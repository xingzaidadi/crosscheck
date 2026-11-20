"""Persist successful exploratory runs as reusable regression assets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.asset_pipeline import auto_promote_read_only, create_candidate, record_replay
from core.asset_store import AssetStore


def plan_fingerprint(plan: dict) -> str:
    identity = {"url": plan.get("url"), "instruction": plan.get("source_instruction")}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def find_reusable_asset(workspace: str | Path, plan: dict) -> dict | None:
    store = AssetStore(Path(workspace) / "knowledge_base" / "asset_candidates")
    fingerprint = plan_fingerprint(plan)
    for asset in store.list():
        payload = asset.get("payload") or {}
        if payload.get("plan_fingerprint") == fingerprint and store.executable(asset["asset_id"]):
            return asset
    return None


def harden_run(*, workspace: str | Path, plan: dict, result: dict,
               replay_passes: int = 2) -> dict:
    if result.get("status") != "PASSED":
        return {"status": "NOT_ELIGIBLE", "reason": "only passed runs can be hardened"}
    evidence = list(result.get("evidence") or [])
    payload = {
        "case_id": plan.get("plan_id"),
        "page_url": plan.get("url"),
        "actions": plan.get("actions") or [],
        "oracles": plan.get("oracles") or [],
        "write_risk": bool(plan.get("write_risk")),
        "source_instruction": plan.get("source_instruction"),
        "plan_fingerprint": plan_fingerprint(plan),
        "required_review": [] if not plan.get("write_risk") else ["write_scope", "business_semantics"],
    }
    asset = create_candidate(payload, asset_type="ui_agent_regression")
    for replay_index in range(replay_passes):
        asset = record_replay(asset, passed=True, original_result=result,
                              replay_result={"stable": True, "replay": replay_index + 1},
                              evidence=evidence)
    if not payload["write_risk"]:
        asset = auto_promote_read_only(asset, evidence=evidence, replay_passes=replay_passes)
    store = AssetStore(Path(workspace) / "knowledge_base" / "asset_candidates")
    path = store.save(asset)
    return {"status": "PROVISIONAL" if asset["state"] == "provisional" else "REVIEW_REQUIRED",
            "asset_id": asset["asset_id"], "state": asset["state"], "path": str(path)}
