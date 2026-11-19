"""Repeated local acceptance runner with residue and fault checks."""
from __future__ import annotations

from typing import Any, Callable


def run_soak(factory: Callable[[int], dict[str, Any]], *, repetitions: int = 5) -> dict[str, Any]:
    results = []
    for index in range(repetitions):
        try:
            result = dict(factory(index + 1) or {})
        except Exception as exc:
            result = {"passed": False, "error": str(exc)}
        result["iteration"] = index + 1
        results.append(result)
    return {"passed": len(results) == repetitions and all(item.get("passed") is True for item in results),
            "repetitions": repetitions, "results": results}


def run_fault_injection(factory: Callable[[str], dict[str, Any]], *, faults: tuple[str, ...] = ("timeout", "handler_error")) -> dict[str, Any]:
    results = []
    for fault in faults:
        try:
            result = dict(factory(fault) or {})
        except Exception as exc:
            result = {"recovered": False, "error": str(exc)}
        result["fault"] = fault
        results.append(result)
    return {"passed": bool(results) and all(item.get("recovered") is True for item in results),
            "faults": results}
