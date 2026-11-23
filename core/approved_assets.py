"""Load human-approved remediation assets without mutating canonical cases."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def _load(path: Path) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix in {".yaml", ".yml"} \
            else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def load_approved_assets(suite_dir: str | Path | None, asset_type: str) -> list[dict[str, Any]]:
    if not suite_dir:
        return []
    root = Path(suite_dir) / "approved_assets" / asset_type
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")) + sorted(root.glob("*.json")):
        data = _load(path)
        health = data.get("health") or {}
        health_status = str(health.get("status") or "").lower() if isinstance(health, dict) else ""
        if data and data.get("status") == "approved" and data.get("approved_by") \
                and health_status not in {"unhealthy", "recertification_pending", "recertification_failed"}:
            rows.append(data)
    return rows


def approved_fixture_for_case(suite_dir: str | Path | None, case_key: str) -> dict[str, Any] | None:
    for fixture in load_approved_assets(suite_dir, "fixtures"):
        if case_key in set(fixture.get("case_keys") or []):
            return fixture
    return None


def approved_oracle_for_case(suite_dir: str | Path | None, case_id: str) -> dict[str, Any] | None:
    for oracle in load_approved_assets(suite_dir, "oracles"):
        if str(oracle.get("case_id") or "") == str(case_id):
            return oracle
    return None
