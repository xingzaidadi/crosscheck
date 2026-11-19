"""Search, create-if-missing, lease and cleanup planning for test objects."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from core.arsenal import Lease, ObjectRecord, claim_object


@dataclass(frozen=True)
class ObjectNeed:
    object_type: str
    desired_state: str
    match: dict[str, Any] = field(default_factory=dict)
    strategy: str = "reuse_or_create"
    create_capability: str = ""
    cleanup_capability: str = ""


def plan_object_lifecycle(
    need: ObjectNeed,
    existing: list[ObjectRecord],
    *,
    run_id: str,
    lease_id: str,
    now: float | None = None,
) -> dict[str, Any]:
    matches = [record for record in existing if record.object_type == need.object_type
               and record.state == need.desired_state
               and all(record.attributes.get(key) == value for key, value in need.match.items())
               and record.status == "active" and not record.lease_id]
    if matches:
        record = matches[0]
        lease = claim_object(record, run_id=run_id, lease_id=lease_id, now=now)
        return {"action": "reuse", "record": record, "lease": lease, "cleanup": None}
    if need.strategy == "reuse_only":
        return {"action": "blocked", "reason": "matching object does not exist"}
    if not need.create_capability:
        return {"action": "blocked", "reason": "create capability is required"}
    identity_seed = json.dumps({"run_id": run_id, "need": need.__dict__}, sort_keys=True, default=str)
    provisional = ObjectRecord(
        need.object_type,
        {"provisional_id": hashlib.sha256(identity_seed.encode()).hexdigest()[:16]},
        need.desired_state,
        attributes=dict(need.match),
        provenance={"run_id": run_id, "created_by": need.create_capability},
    )
    lease = claim_object(provisional, run_id=run_id, lease_id=lease_id, now=now)
    cleanup = {"capability": need.cleanup_capability, "required": True} if need.cleanup_capability else {
        "required": True, "manual_required": True,
    }
    return {"action": "create_if_missing", "record": provisional, "lease": lease,
            "create": {"capability": need.create_capability}, "cleanup": cleanup}


def execute_object_lifecycle(
    plan: dict[str, Any],
    handlers: dict[str, Callable[..., dict[str, Any]]],
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if plan.get("action") == "blocked":
        return {"status": "blocked", "reason": plan.get("reason")}
    result = {"status": "ready", "action": plan["action"], "record": plan["record"]}
    if plan["action"] == "create_if_missing":
        capability = plan["create"]["capability"]
        handler = handlers.get(capability)
        if handler is None:
            return {"status": "blocked", "reason": f"missing handler: {capability}"}
        result["creation"] = handler(context=dict(context or {}), record=plan["record"])
    result["cleanup"] = plan.get("cleanup")
    return result
