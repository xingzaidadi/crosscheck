"""Build review queues and safely promote replay-proven UI assets."""
from __future__ import annotations

from typing import Any

from core.asset_store import AssetStore


def review_queue(store: AssetStore) -> list[dict[str, Any]]:
    rows = []
    for asset in store.list():
        if asset.get("state") not in {"candidate", "replay_verified"}:
            continue
        payload = asset.get("payload") or {}
        rows.append({
            "asset_id": asset.get("asset_id"),
            "state": asset.get("state"),
            "asset_type": asset.get("asset_type"),
            "case_id": payload.get("case_id"),
            "replay_attempts": int(asset.get("replay_attempts") or 0),
            "drift_rate": float(asset.get("drift_rate") or 0),
            "evidence": list(asset.get("evidence") or []),
            "required_review": list(payload.get("required_review") or []),
        })
    return sorted(rows, key=lambda row: (row["state"] != "replay_verified", row["case_id"] or ""))


def accept_replay_verified(store: AssetStore, asset_id: str, *, reviewer: str,
                           evidence: list[str] | None = None) -> dict[str, Any]:
    asset = store.load(asset_id)
    if asset.get("state") != "replay_verified":
        raise ValueError("asset must be replay_verified before human review")
    if int(asset.get("replay_attempts") or 0) < 1 or not asset.get("evidence"):
        raise ValueError("asset requires replay attempts and evidence")
    updated = store.promote(asset_id, "human_verified", evidence=evidence)
    updated["review"] = {"reviewer": reviewer, "decision": "accepted"}
    store.save(updated)
    return updated


def activate_reviewed(store: AssetStore, asset_id: str, *, reviewer: str,
                      evidence: list[str] | None = None) -> dict[str, Any]:
    """Approve and activate a human-reviewed asset without skipping governance states."""
    asset = store.load(asset_id)
    if asset.get("state") != "human_verified":
        raise ValueError("asset must be human_verified before activation")
    updated = store.promote(asset_id, "approved", evidence=evidence)
    updated = store.promote(asset_id, "active", evidence=evidence)
    updated["activation"] = {"reviewer": reviewer, "decision": "active"}
    store.save(updated)
    return updated
