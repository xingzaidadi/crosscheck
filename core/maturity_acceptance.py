"""Offline maturity gates for the four autonomous UI delivery phases."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class MaturityGate:
    phase: str
    target: str
    passed: bool
    score: float
    evidence: list[str]


def evaluate_maturity(samples: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(samples)
    if not total:
        return {"status": "INSUFFICIENT_DATA", "score": 0.0, "gates": []}
    natural = sum(bool(item.get("plan")) and item.get("status") not in {"NEEDS_INPUT"} for item in samples) / total
    autonomous = sum(item.get("status") == "PASSED" and item.get("execution") is not None for item in samples) / total
    recoverable = sum(bool(item.get("execution", {}).get("recovery_events") is not None) for item in samples) / total
    eligible = [item for item in samples if item.get("status") == "PASSED"]
    hardened = (sum(item.get("hardening", {}).get("status") == "PROVISIONAL" for item in eligible) / len(eligible)) \
        if eligible else 0.0
    safety = sum(not any(
        row.get("risk", {}).get("level") == "destructive" and row.get("ok")
        for row in item.get("execution", {}).get("actions", [])
    ) for item in samples) / total
    gates = [
        MaturityGate("1-natural-language", ">=80% intake plans", natural >= .8, natural, ["plan generated"]),
        MaturityGate("2-autonomous-exploration", ">=85% executable runs", autonomous >= .85, autonomous, ["runtime execution"]),
        MaturityGate("2-recovery", "recovery trace present", recoverable >= .9, recoverable, ["recovery_events"]),
        MaturityGate("3-hardening", ">=80% provisional assets", hardened >= .8, hardened, ["hardening status"]),
        MaturityGate("4-safety", "no destructive bypass", safety == 1.0, safety, ["risk policy"]),
    ]
    score = round((natural * .2 + autonomous * .3 + recoverable * .15 + hardened * .2 + safety * .15) * 100, 2)
    return {"status": "PASSED" if score >= 90 and all(gate.passed for gate in gates) else "NOT_READY",
            "score": score, "gates": [asdict(gate) for gate in gates], "sample_count": total}
