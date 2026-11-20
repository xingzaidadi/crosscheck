"""Promote captured UI/API assets through explicit review states."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


STATES = ("candidate", "replay_verified", "provisional", "human_verified", "approved", "active", "healthy", "retired")
TRANSITIONS = {"candidate": {"replay_verified", "retired"},
               "replay_verified": {"provisional", "human_verified", "retired"},
               "provisional": {"human_verified", "approved", "active", "healthy", "retired"},
               "human_verified": {"approved", "retired"},
               "approved": {"active", "healthy", "retired"},
               "active": {"healthy", "retired"}, "healthy": {"retired"}, "retired": set()}


def create_candidate(capture: dict[str, Any], *, asset_type: str = "ui_action") -> dict[str, Any]:
    payload = copy.deepcopy(capture)
    payload.setdefault("parameters", {})
    return {"asset_id": "asset-" + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16],
            "asset_type": asset_type, "state": "candidate", "payload": payload, "evidence": []}


def promote(asset: dict[str, Any], target: str, *, evidence: list[str] | None = None) -> dict[str, Any]:
    current = str(asset.get("state") or "candidate")
    if target not in STATES or target not in TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid asset transition: {current} -> {target}")
    updated = copy.deepcopy(asset)
    updated["state"] = target
    updated["evidence"] = sorted(set(updated.get("evidence") or []) | set(evidence or []))
    return updated


def can_execute(asset: dict[str, Any]) -> bool:
    return asset.get("state") in {"provisional", "active", "healthy"} and bool(asset.get("evidence")) \
        and float(asset.get("drift_rate") or 0) <= float(asset.get("max_drift_rate") or 0.2)


def auto_promote_read_only(asset: dict[str, Any], *, evidence: list[str],
                           replay_passes: int = 2) -> dict[str, Any]:
    """Promote stable read-only assets without bypassing write-risk review."""
    payload = asset.get("payload") or {}
    if payload.get("write_risk"):
        raise ValueError("write-risk assets require human review")
    if int(asset.get("replay_attempts") or 0) < replay_passes:
        raise ValueError(f"at least {replay_passes} successful replays are required")
    if int(asset.get("replay_failures") or 0):
        raise ValueError("assets with replay failures cannot be auto-promoted")
    if asset.get("state") != "replay_verified":
        raise ValueError("asset must be replay_verified")
    updated = promote(asset, "provisional", evidence=evidence)
    updated["auto_promotion"] = {"policy": "stable_read_only", "replay_passes": replay_passes}
    return updated


def record_replay(asset: dict[str, Any], *, passed: bool, original_result: Any,
                  replay_result: Any, evidence: list[str] | None = None) -> dict[str, Any]:
    """Record isolated replay evidence before a human can approve an asset."""
    updated = copy.deepcopy(asset)
    attempts = int(updated.get("replay_attempts") or 0) + 1
    failures = int(updated.get("replay_failures") or 0) + (0 if passed else 1)
    updated["replay_attempts"] = attempts
    updated["replay_failures"] = failures
    updated["drift_rate"] = round(failures / attempts, 4)
    updated.setdefault("replays", []).append({
        "passed": passed,
        "original_hash": hashlib.sha256(json.dumps(original_result, sort_keys=True, default=str).encode()).hexdigest(),
        "replay_hash": hashlib.sha256(json.dumps(replay_result, sort_keys=True, default=str).encode()).hexdigest(),
        "evidence": list(evidence or []),
    })
    if passed and updated.get("state") == "candidate":
        updated = promote(updated, "replay_verified", evidence=evidence)
    return updated


def candidate_from_capture(capture: dict[str, Any], *, asset_type: str = "ui_action",
                           sensitive_keys: set[str] | None = None) -> dict[str, Any]:
    """Create a parameterized candidate from a captured request/action."""
    candidate = create_candidate(capture, asset_type=asset_type)
    sensitive_keys = sensitive_keys or {"password", "token", "authorization", "cookie", "secret"}
    payload = candidate["payload"]

    def sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: ("{{secret}}" if key.lower() in sensitive_keys else sanitize(item))
                    for key, item in value.items()}
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    candidate["payload"] = sanitize(payload)
    candidate["parameterized"] = True
    return candidate
