"""Case v2 contract, migration and deterministic validation."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


V2_REQUIRED = {"schema_version", "case_id", "title", "traceability", "intent", "preconditions", "action", "oracles"}
ORACLE_PROOFS = {"ui", "api", "db", "event", "manual"}
ORACLE_OPERATORS = {"equals", "not_equals", "contains", "exists", "matches", "gte", "lte", "in"}


def migrate_v1(case: dict[str, Any]) -> dict[str, Any]:
    """Convert the existing canonical shape to a conservative v2 draft."""
    if int(case.get("schema_version") or 1) >= 2:
        return copy.deepcopy(case)
    migrated = copy.deepcopy(case)
    migrated["schema_version"] = 2
    migrated.setdefault("traceability", {"requirements": [], "rules": [], "risks": []})
    actions = case.get("actions") or []
    if isinstance(actions, dict):
        flattened = []
        for layer, items in actions.items():
            values = items if isinstance(items, list) else [items]
            for item in values:
                if isinstance(item, dict):
                    flattened.append({"layer": layer, **item})
        actions = flattened
    first_action = actions[0] if actions and isinstance(actions[0], dict) else {}
    migrated.setdefault("intent", {
        "target_object": str(case.get("feature") or "unknown"),
        "target_action": str(first_action.get("name") or first_action.get("action") or "verify"),
        "scenario": str(case.get("scenario_type") or "unspecified"),
        "under_test": str(case.get("feature") or case.get("case_id")),
    })
    migrated.setdefault("preconditions", [])
    action = first_action
    migrated["action"] = migrated.get("action") or {
        "capability": action.get("capability") or action.get("action_ref") or str(case.get("case_id")),
        "inputs": action.get("inputs") or {},
    }
    oracles = []
    for proof, items in (case.get("assertions") or {}).items():
        if proof == "source_text" or not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            oracles.append({
                "id": str(item.get("id") or f"{proof}-{index + 1}"),
                "subject": item.get("path") or item.get("field") or item.get("name") or proof,
                "operator": item.get("operator") or "exists",
                "expected": item.get("expected"),
                "proof": "ui" if proof == "ui" else "api" if proof == "api" else "db" if proof == "db" else "manual",
            })
    migrated["oracles"] = migrated.get("oracles") or oracles
    migrated.setdefault("wait", {})
    migrated.setdefault("open_questions", [])
    return migrated


def validate_v2(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(V2_REQUIRED - set(case))
    errors.extend(f"missing key: {key}" for key in missing)
    if case.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    if not isinstance(case.get("traceability"), dict):
        errors.append("traceability must be an object")
    intent = case.get("intent")
    if not isinstance(intent, dict) or not intent.get("under_test"):
        errors.append("intent.under_test is required")
    action = case.get("action")
    if not isinstance(action, dict) or not action.get("capability"):
        errors.append("action.capability is required")
    if not isinstance(case.get("preconditions"), list):
        errors.append("preconditions must be a list")
    seen: set[str] = set()
    for oracle in case.get("oracles") or []:
        if not isinstance(oracle, dict):
            errors.append("oracle must be an object")
            continue
        oid = str(oracle.get("id") or "")
        if not oid or oid in seen:
            errors.append(f"oracle id must be unique: {oid or '<empty>'}")
        seen.add(oid)
        if oracle.get("proof") not in ORACLE_PROOFS:
            errors.append(f"unsupported oracle proof: {oracle.get('proof')}")
        if oracle.get("operator") not in ORACLE_OPERATORS:
            errors.append(f"unsupported oracle operator: {oracle.get('operator')}")
        if not oracle.get("subject"):
            errors.append(f"oracle subject is required: {oid}")
    wait = case.get("wait") or {}
    if wait and (float(wait.get("timeout_s", 1)) <= 0 or float(wait.get("interval_s", 1)) <= 0):
        errors.append("wait timeout_s and interval_s must be positive")
    return errors


def oracle_evidence(case: dict[str, Any], *, api: Any = None, ui: Any = None,
                    db: Any = None, event: Any = None, manual: Any = None) -> dict[str, Any]:
    """Build the proof namespace used by the v2 oracle evaluator."""
    return {"api": api, "ui": ui, "db": db, "event": event, "manual": manual}


def wait_config(case: dict[str, Any]) -> dict[str, Any]:
    wait = dict(case.get("wait") or {})
    return {"until": str(wait.get("until") or ""),
            "timeout_s": float(wait.get("timeout_s") or 0),
            "interval_s": float(wait.get("interval_s") or 1)}


def content_hash(case: dict[str, Any]) -> str:
    clean = {k: v for k, v in case.items() if k not in {"approval", "compiled"}}
    return hashlib.sha256(json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def to_legacy_execution(case: dict[str, Any]) -> dict[str, Any]:
    """Project v2 into the current deterministic executor shape.

    The projection preserves v2 intent and oracles in ``raw`` while allowing
    existing adapters to execute the action before their native v2 bindings
    are introduced.
    """
    projected = copy.deepcopy(case)
    action = dict(case.get("action") or {})
    oracle_groups: dict[str, list[dict[str, Any]]] = {}
    bindings: dict[str, dict[str, Any]] = {}
    for oracle in case.get("oracles") or []:
        proof = str(oracle.get("proof") or "manual")
        item = {"id": oracle.get("id"), "subject": oracle.get("subject"),
                "operator": oracle.get("operator"), "expected": oracle.get("expected")}
        oracle_groups.setdefault(proof, []).append(item)
        bindings[str(oracle["id"])] = {"layer": proof, "proof": proof, "ref": str(oracle.get("subject"))}
    layer_names = {"ui": "ui", "api": "api", "db": "db", "event": "script", "manual": "manual"}
    required = [layer_names.get(str(oracle.get("proof")), "manual") for oracle in case.get("oracles") or []]
    projected["layers"] = {"required": sorted(set(required))}
    projected["assertions"] = {layer_names.get(key, key): value for key, value in oracle_groups.items()}
    projected["actions"] = [{"capability": action.get("capability"), "inputs": action.get("inputs") or {}}]
    execution = dict(case.get("execution") or {})
    execution.setdefault("mode", str(action.get("mode") or "api"))
    execution.setdefault("feature", str((case.get("intent") or {}).get("under_test") or ""))
    execution.setdefault("action_ref", str(action.get("capability") or ""))
    execution.setdefault("engine_assertions", projected["assertions"])
    execution.setdefault("assertion_bindings", bindings)
    execution.setdefault("data_prep", list(case.get("preconditions") or []))
    projected["execution"] = execution
    projected["status"] = "ready" if case.get("status") == "ready" else str(case.get("status") or "draft")
    projected["raw_v2"] = copy.deepcopy(case)
    return projected
