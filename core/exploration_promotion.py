"""Promote reviewed exploration assets into suite-local assertion bindings."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from core.asset_store import AssetStore


def apply_exploration_asset(
    asset_id: str,
    *,
    workspace: str | Path,
    suite: str | Path,
    proof_ref: str,
) -> dict[str, Any]:
    workspace_path = Path(workspace).resolve()
    suite_path = Path(suite).resolve()
    try:
        suite_path.relative_to(workspace_path)
    except ValueError as exc:
        raise ValueError("suite must stay inside workspace") from exc
    store = AssetStore(workspace_path / "knowledge_base" / "asset_candidates")
    asset = store.load(asset_id)
    if asset.get("state") not in {"human_verified", "approved", "healthy"}:
        raise ValueError("exploration asset requires human_verified review before binding")
    payload = asset.get("payload") or {}
    case_id = str((asset.get("source") or {}).get("case_id") or payload.get("case_id") or "")
    assertion_id = str((asset.get("source") or {}).get("assertion_id") or payload.get("assertion_id") or "")
    case_key = case_id.split("/")[-1].split("-", 1)[0]
    binding_path = suite_path / "ui_bindings" / f"{case_key}.yaml"
    if not binding_path.is_file():
        raise FileNotFoundError(f"reviewed UI binding not found: {binding_path}")
    data = yaml.safe_load(binding_path.read_text(encoding="utf-8")) or {}
    raw = dict(data.get("raw") or {})
    bindings = dict(raw.get("assertion_bindings") or {})
    bindings[assertion_id] = {"layer": "ui", "proof": "ui_check", "ref": proof_ref,
                              "asset_id": asset_id}
    raw["assertion_bindings"] = bindings
    dependencies = list(raw.get("knowledge_dependencies") or [])
    dependency = {"kind": "exploration_asset", "asset_id": asset_id,
                  "evidence": list(asset.get("evidence") or [])}
    if dependency not in dependencies:
        dependencies.append(dependency)
    raw["knowledge_dependencies"] = dependencies
    data["raw"] = raw
    binding_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"asset_id": asset_id, "case_key": case_key, "assertion_id": assertion_id,
            "binding": str(binding_path), "proof_ref": proof_ref}
