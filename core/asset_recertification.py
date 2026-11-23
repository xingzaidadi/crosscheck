"""Re-certify degraded or unhealthy approved assets with explicit evidence."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


STATES = {"healthy", "degraded", "unhealthy", "recertification_pending", "recertification_failed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)


def asset_path(suite_dir: str | Path, asset_type: str, asset_id: str) -> Path:
    folder = "fixtures" if asset_type == "fixture" else "oracles"
    return Path(suite_dir) / "approved_assets" / folder / f"{_safe(asset_id)}.yaml"


def load_asset(suite_dir: str | Path, asset_type: str, asset_id: str) -> dict[str, Any]:
    path = asset_path(suite_dir, asset_type, asset_id)
    if not path.is_file():
        raise FileNotFoundError(asset_id)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or data.get("status") != "approved" or not data.get("approved_by"):
        raise ValueError("asset must be approved before recertification")
    return data


def _save(path: Path, asset: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(yaml.safe_dump(asset, allow_unicode=True, sort_keys=False), encoding="utf-8")
    temporary.replace(path)


def request_recertification(
    suite_dir: str | Path,
    asset_type: str,
    asset_id: str,
    *,
    requester: str,
    reason: str,
) -> dict[str, Any]:
    if not requester.strip() or not reason.strip():
        raise ValueError("requester and reason are required")
    path = asset_path(suite_dir, asset_type, asset_id)
    asset = load_asset(suite_dir, asset_type, asset_id)
    health = asset.get("health") or {}
    current = str(health.get("status") or "unknown")
    if current not in {"degraded", "unhealthy", "recertification_failed", "unknown"}:
        raise ValueError(f"asset does not need recertification: {current}")
    asset["health"] = {**health, "status": "recertification_pending"}
    asset["recertification"] = {
        "status": "pending", "requested_by": requester, "requested_at": _now(),
        "reason": reason, "evidence": [], "soak_runs": 0,
    }
    _save(path, asset)
    return {"asset_id": asset_id, "asset_type": asset_type, "status": "recertification_pending",
            "path": str(path)}


def submit_recertification_evidence(
    suite_dir: str | Path,
    asset_type: str,
    asset_id: str,
    *,
    submitter: str,
    soak_runs: int,
    passed_runs: int,
    evidence: list[str],
) -> dict[str, Any]:
    if not submitter.strip() or soak_runs < 1 or passed_runs < 0 or passed_runs > soak_runs:
        raise ValueError("submitter and valid soak run counts are required")
    if not evidence:
        raise ValueError("recertification evidence is required")
    path = asset_path(suite_dir, asset_type, asset_id)
    asset = load_asset(suite_dir, asset_type, asset_id)
    request = asset.get("recertification") or {}
    if request.get("status") != "pending":
        raise ValueError("asset must have a pending recertification request")
    passed = passed_runs == soak_runs
    result = {
        "status": "evidence_submitted" if passed else "failed",
        "submitted_by": submitter, "submitted_at": _now(), "soak_runs": soak_runs,
        "passed_runs": passed_runs, "pass_rate": round(passed_runs / soak_runs, 4),
        "evidence": list(evidence),
    }
    asset["recertification"] = {**request, **result}
    asset["health"] = {**(asset.get("health") or {}),
                        "status": "recertification_pending" if passed else "recertification_failed"}
    _save(path, asset)
    return {"asset_id": asset_id, "asset_type": asset_type, **result, "path": str(path)}


def approve_recertification(
    suite_dir: str | Path,
    asset_type: str,
    asset_id: str,
    *,
    reviewer: str,
    minimum_soak_runs: int = 5,
) -> dict[str, Any]:
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    path = asset_path(suite_dir, asset_type, asset_id)
    asset = load_asset(suite_dir, asset_type, asset_id)
    request = asset.get("recertification") or {}
    if request.get("status") != "evidence_submitted":
        raise ValueError("recertification evidence has not passed")
    if int(request.get("soak_runs") or 0) < minimum_soak_runs:
        raise ValueError(f"at least {minimum_soak_runs} soak runs are required")
    if int(request.get("passed_runs") or 0) != int(request.get("soak_runs") or 0):
        raise ValueError("all recertification soak runs must pass")
    content = {key: value for key, value in asset.items() if key not in {"health", "recertification"}}
    content_hash = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    asset["content_hash"] = content_hash
    asset["health"] = {**(asset.get("health") or {}), "status": "healthy",
                        "recertified_at": _now(), "recertified_by": reviewer,
                        "last_soak_runs": request["soak_runs"], "success_rate": 1.0,
                        "consecutive_failures": 0}
    asset["recertification"] = {**request, "status": "approved", "reviewed_by": reviewer,
                                "reviewed_at": _now()}
    _save(path, asset)
    return {"asset_id": asset_id, "asset_type": asset_type, "status": "healthy",
            "reviewer": reviewer, "content_hash": content_hash, "path": str(path)}
