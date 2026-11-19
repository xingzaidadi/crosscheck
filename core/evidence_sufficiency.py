"""Decide whether available evidence proves the stated test objective.

Technology names in a case do not automatically require direct access to that
technology.  A business-behaviour case may be conclusively proved through the
public UI and persisted application state.  Direct producer/provider evidence
is required only when the objective explicitly tests the integration itself.
"""
from __future__ import annotations

from typing import Any


OBJECTIVE_POLICIES = {
    "business_behavior": {
        "accepted_sets": [
            {"ui", "db"},
            {"ui", "api"},
            {"api", "db"},
            {"ui", "api", "db"},
        ],
        "requires_provider": False,
    },
    "integration_result": {
        "accepted_sets": [
            {"ui", "db"},
            {"api", "db"},
            {"ui", "api", "db"},
        ],
        "requires_provider": False,
    },
    "integration_transport": {
        "accepted_sets": [{"provider", "consumer"}, {"provider", "api", "db"}],
        "requires_provider": True,
    },
}


def assess_evidence(
    objective: str,
    evidence_layers: set[str] | list[str],
    *,
    assertions_passed: bool,
    residue_clean: bool = True,
) -> dict[str, Any]:
    policy = OBJECTIVE_POLICIES.get(objective)
    if policy is None:
        return {"sufficient": False, "verdict": "INCONCLUSIVE", "reason": "unknown objective"}
    available = set(evidence_layers)
    matched = next((required for required in policy["accepted_sets"] if required <= available), None)
    if not assertions_passed:
        return {"sufficient": True, "verdict": "FAIL", "reason": "objective assertions failed"}
    if not residue_clean:
        return {"sufficient": False, "verdict": "CLEANUP_FAILED", "reason": "test residue remains"}
    if matched is None:
        return {"sufficient": False, "verdict": "INCONCLUSIVE",
                "reason": "available evidence does not prove the objective"}
    return {"sufficient": True, "verdict": "PASS", "reason": "objective proved",
            "proof_layers": sorted(matched), "provider_required": policy["requires_provider"]}


def infer_objective(case: dict[str, Any]) -> str:
    """Use an explicit objective first; conservatively infer transport tests."""
    explicit = str((case.get("intent") or {}).get("verification_scope") or
                   case.get("verification_scope") or "")
    if explicit in OBJECTIVE_POLICIES:
        return explicit
    actions = case.get("actions") or {}
    assertions = case.get("assertions") or {}
    text = " ".join(str(value or "") for value in (
        case.get("title"), case.get("steps"), case.get("expected"), case.get("notes"),
        actions.get("source_text") if isinstance(actions, dict) else actions,
        assertions.get("source_text") if isinstance(assertions, dict) else assertions,
    )).lower()
    transport_phrases = ("消息投递", "消息消费", "mq producer", "回调签名", "第三方接口调用", "传输链路")
    return "integration_transport" if any(phrase in text for phrase in transport_phrases) \
        else "business_behavior"
