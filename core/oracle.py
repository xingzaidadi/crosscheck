"""Deterministic Case v2 oracle evaluation."""
from __future__ import annotations

import re
import time
from typing import Any


_MISSING = object()


def dig(value: Any, path: str) -> Any:
    current = value
    for part in str(path or "").replace("[", ".").replace("]", "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            if part not in current:
                return _MISSING
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return _MISSING
    return current


def evaluate_one(oracle: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    subject = str(oracle.get("subject") or "")
    actual = dig(evidence, subject)
    expected = oracle.get("expected")
    operator = str(oracle.get("operator") or "exists")
    if actual is _MISSING:
        passed = operator == "not_equals"
        actual_value = None
    else:
        actual_value = actual
        passed = _apply(operator, actual, expected)
    return {"id": str(oracle.get("id") or ""), "subject": subject,
            "operator": operator, "expected": expected, "actual": actual_value,
            "passed": passed, "proof": oracle.get("proof")}


def evaluate(oracles: list[dict[str, Any]], evidence: dict[str, Any]) -> dict[str, Any]:
    results = [evaluate_one(oracle, evidence) for oracle in oracles]
    return {"passed": all(item["passed"] for item in results), "results": results,
            "failed": [item["id"] for item in results if not item["passed"]]}


def poll(oracles: list[dict[str, Any]], evidence_supplier, *, until: str = "",
         timeout_s: float = 0, interval_s: float = 1) -> dict[str, Any]:
    """Poll evidence until all oracles pass or the deadline expires."""
    deadline = time.monotonic() + max(0.0, timeout_s)
    last = evaluate(oracles, evidence_supplier())
    while not last["passed"] and timeout_s > 0 and time.monotonic() < deadline:
        time.sleep(max(0.01, interval_s))
        last = evaluate(oracles, evidence_supplier())
    if until:
        matched = next((item for item in last["results"] if item["id"] == until), None)
        last["until"] = until
        last["until_passed"] = bool(matched and matched["passed"])
        last["passed"] = last["passed"] and last["until_passed"]
    last["timed_out"] = not last["passed"] and timeout_s > 0 and time.monotonic() >= deadline
    return last


def _apply(operator: str, actual: Any, expected: Any) -> bool:
    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "contains":
        return expected in actual
    if operator == "exists":
        return actual is not None
    if operator == "matches":
        return re.search(str(expected), str(actual)) is not None
    if operator == "gte":
        return actual >= expected
    if operator == "lte":
        return actual <= expected
    if operator == "in":
        return actual in expected
    return False
