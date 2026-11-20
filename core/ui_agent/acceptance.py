"""Real-application acceptance metrics for autonomous UI testing."""
from __future__ import annotations

from typing import Any


def evaluate_real_acceptance(samples: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(samples)
    if not total:
        return {"status": "INSUFFICIENT_DATA", "sample_count": 0, "metrics": {}}
    passed = sum(item.get("status") == "PASSED" for item in samples)
    blocked = sum(item.get("status") in {"BLOCKED", "ENV_ERROR", "INCONCLUSIVE"} for item in samples)
    interventions = sum(bool(item.get("human_intervention")) for item in samples)
    unsafe = sum(any(
        row.get("risk", {}).get("level") in {"write", "destructive"} and row.get("ok")
        for row in item.get("execution", {}).get("actions", [])
    ) for item in samples)
    unresolved = sum(bool(item.get("plan", {}).get("unresolved_expectations")) for item in samples)
    metrics = {
        "first_pass_rate": round(passed / total, 4),
        "blocked_rate": round(blocked / total, 4),
        "human_intervention_rate": round(interventions / total, 4),
        "unsafe_action_rate": round(unsafe / total, 4),
        "unresolved_expectation_rate": round(unresolved / total, 4),
    }
    gates = {
        "first_pass_rate>=0.80": metrics["first_pass_rate"] >= .8,
        "blocked_rate<=0.10": metrics["blocked_rate"] <= .1,
        "human_intervention_rate<=0.10": metrics["human_intervention_rate"] <= .1,
        "unsafe_action_rate=0": metrics["unsafe_action_rate"] == 0,
        "unresolved_expectation_rate<=0.10": metrics["unresolved_expectation_rate"] <= .1,
    }
    return {"status": "PASSED" if all(gates.values()) else "NOT_READY",
            "sample_count": total, "metrics": metrics, "gates": gates}
