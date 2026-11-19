"""Discover and validate reusable business skill packs in a workspace."""
from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


@dataclass(frozen=True)
class BusinessSkill:
    skill_id: str
    version: str
    root: Path
    manifest: dict[str, Any]

    @property
    def system_keys(self) -> list[str]:
        return [str(item) for item in self.manifest.get("system_keys") or []]

    @property
    def provides(self) -> list[str]:
        return [str(item) for item in self.manifest.get("provides") or []]

    def path(self, relative: str) -> Path:
        candidate = (self.root / relative).resolve()
        try:
            candidate.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError(f"skill path escapes pack: {candidate}") from exc
        return candidate

    def read_yaml(self, relative: str) -> dict[str, Any]:
        path = self.path(relative)
        if not path.is_file():
            return {}
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return value if isinstance(value, dict) else {}

    def compatible(self, url: str) -> bool:
        parsed = urlparse(url)
        match = self.manifest.get("match") or {}
        hosts = [str(item).lower() for item in match.get("hosts") or []]
        paths = [str(item) for item in match.get("paths") or []]
        host_ok = not hosts or parsed.netloc.lower() in hosts
        path_ok = not paths or any(fnmatch.fnmatch(parsed.path, item) for item in paths)
        return host_ok and path_ok

    def context(self, url: str, *, cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        features = []
        for case in cases or []:
            features.extend([str(item) for item in (case.get("business_tags") or [])])
            execution = case.get("execution") or {}
            if execution.get("feature"):
                features.append(str(execution["feature"]))
        return {
            "skill_id": self.skill_id,
            "version": self.version,
            "root": str(self.root),
            "url": url,
            "features": sorted(set(features)),
            "system_keys": self.system_keys,
            "provides": self.provides,
            "profiles": self.manifest.get("profiles") or [],
            "sessions": self.manifest.get("sessions") or {},
            "health": self.health(),
        }

    def asset_documents(self, kind: str) -> list[dict[str, Any]]:
        documents = []
        for relative in ((self.manifest.get("assets") or {}).get(kind) or []):
            value = self.read_yaml(str(relative))
            if value:
                documents.append({"path": str(relative), "value": value})
        return documents

    def page_model(self, url: str) -> dict[str, Any]:
        parsed = urlparse(url)
        best: tuple[int, dict[str, Any]] | None = None
        for document in self.asset_documents("page_models"):
            value = document["value"]
            entry_url = str((value.get("entry") or {}).get("url") or "")
            score = len(urlparse(entry_url).path) if entry_url and parsed.path.startswith(urlparse(entry_url).path) else 0
            if best is None or score > best[0]:
                best = (score, value)
        return best[1] if best else {}

    def actions(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for document in self.asset_documents("actions"):
            merged.update(document["value"].get("actions") or {})
        return merged

    def assertions(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for document in self.asset_documents("assertions"):
            merged.update(document["value"].get("assertions") or {})
        return merged

    def fingerprint(self) -> str:
        payload = []
        for kind in ("page_models", "actions", "assertions", "workflows"):
            for document in self.asset_documents(kind):
                payload.append((document["path"], document["value"]))
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def health(self) -> dict[str, Any]:
        health_path = self.root / "health.json"
        current = self.fingerprint()
        if not health_path.is_file():
            return {"status": "UNVERIFIED", "fingerprint": current}
        try:
            value = json.loads(health_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"status": "INVALID", "fingerprint": current}
        expected = str(value.get("fingerprint") or "")
        status = str(value.get("status") or "UNVERIFIED")
        if expected and expected != current:
            status = "STALE"
        return {**value, "status": status, "fingerprint": current}

    def record_health(self, *, status: str, evidence: list[str] | None = None,
                      run_id: str = "") -> Path:
        value = {"skill_id": self.skill_id, "version": self.version, "status": status,
                 "fingerprint": self.fingerprint(), "run_id": run_id,
                 "evidence": list(evidence or [])}
        path = self.root / "health.json"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def _load_pack(path: Path) -> BusinessSkill | None:
    manifest_path = path / "manifest.yaml"
    if not manifest_path.is_file():
        return None
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, yaml.YAMLError):
        return None
    if not isinstance(manifest, dict) or not manifest.get("skill_id"):
        return None
    return BusinessSkill(str(manifest["skill_id"]), str(manifest.get("version") or "0.0.0"),
                         path.resolve(), manifest)


def discover_skills(workspace: str | Path) -> list[BusinessSkill]:
    root = Path(workspace).resolve() / "business_skills"
    if not root.is_dir():
        return []
    return sorted((skill for path in root.iterdir() if path.is_dir()
                   for skill in [_load_pack(path)] if skill), key=lambda item: item.skill_id)


def match_skill(workspace: str | Path, url: str, *, skill_id: str = "") -> BusinessSkill | None:
    skills = discover_skills(workspace)
    if skill_id:
        return next((item for item in skills if item.skill_id == skill_id), None)
    matches = [item for item in skills if item.compatible(url)]
    return matches[0] if len(matches) == 1 else (matches[0] if matches else None)


def write_context(path: str | Path, context: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
