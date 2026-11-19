"""Feature-level frozen acceptance gate."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeatureGate:
    feature_id: str
    required_cases: tuple[str, ...]
    require_soak: bool = False
    require_fault_injection: bool = False
    require_zero_residue: bool = True


def evaluate(gate: FeatureGate, results: list[dict[str, Any]], *, soak_passed: bool = False,
             fault_injection_passed: bool = False, residue_count: int = 0) -> dict[str, Any]:
    indexed = {str(item.get("case_id")): item for item in results}
    missing = [case_id for case_id in gate.required_cases if case_id not in indexed]
    failed = [case_id for case_id in gate.required_cases if case_id in indexed and indexed[case_id].get("verdict") != "PASS"]
    reasons = []
    if missing:
        reasons.append("missing_required_cases")
    if failed:
        reasons.append("failed_required_cases")
    if gate.require_soak and not soak_passed:
        reasons.append("soak_not_passed")
    if gate.require_fault_injection and not fault_injection_passed:
        reasons.append("fault_injection_not_passed")
    if gate.require_zero_residue and residue_count:
        reasons.append("residue_detected")
    return {"feature_id": gate.feature_id, "done": not reasons, "reasons": reasons,
            "missing": missing, "failed": failed, "residue_count": residue_count}
