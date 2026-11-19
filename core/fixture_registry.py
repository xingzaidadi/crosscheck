"""Suite-local fixture registry for reusable, auditable data preconditions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_registry(suite_dir: str | Path) -> dict[str, Any]:
    path = Path(suite_dir) / "fixtures.yaml"
    if not path.exists():
        return {"schema_version": 1, "fixtures": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or not isinstance(data.get("fixtures", {}), dict):
        raise ValueError(f"invalid fixture registry: {path}")
    return data


def fixture_for_case(registry: dict[str, Any], case_key: str) -> dict[str, Any] | None:
    for name, fixture in (registry.get("fixtures") or {}).items():
        if case_key in set(fixture.get("case_keys") or []):
            return {"name": name, **fixture}
    return None


def registry_summary(registry: dict[str, Any]) -> dict[str, Any]:
    fixtures = registry.get("fixtures") or {}
    return {
        "total": len(fixtures),
        "verified": sum(bool(item.get("verified")) for item in fixtures.values()),
        "case_bindings": sum(len(item.get("case_keys") or []) for item in fixtures.values()),
        "unverified": sorted(name for name, item in fixtures.items() if not item.get("verified")),
    }


def write_registry(registry: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(registry, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return target


def write_summary(registry: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(registry_summary(registry), ensure_ascii=False, indent=2), encoding="utf-8")
    return target
