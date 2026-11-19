"""Deterministic case quality and readiness auditor."""
from __future__ import annotations

from typing import Any

from .case_v2 import validate_v2


AMBIGUOUS = ("成功", "正常", "正确", "尽快", "适当", "相关", "正常显示")


def audit_case(case: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    errors = validate_v2(case) if int(case.get("schema_version") or 1) == 2 else []
    for error in errors:
        issues.append({"kind": "schema", "severity": "error", "message": error})
    intent = case.get("intent") or {}
    if not intent.get("under_test"):
        issues.append({"kind": "intent", "severity": "error", "message": "missing intent.under_test"})
    if not (case.get("actors") or case.get("actor")):
        issues.append({"kind": "role", "severity": "error", "message": "missing actor/role"})
    if not case.get("traceability") and not (case.get("source") or {}).get("traceability"):
        issues.append({"kind": "source", "severity": "warning", "message": "missing traceability"})
    for question in case.get("open_questions") or []:
        issues.append({"kind": "open_question", "severity": "error", "message": str(question)})
    text = " ".join(str(case.get(key) or "") for key in ("title", "notes", "expected", "description"))
    for word in AMBIGUOUS:
        if word in text:
            issues.append({"kind": "ambiguity", "severity": "warning", "message": f"ambiguous term: {word}"})
    if int(case.get("schema_version") or 1) == 2:
        for item in case.get("preconditions") or []:
            if not isinstance(item, dict) or not item.get("object"):
                issues.append({"kind": "precondition", "severity": "error", "message": "precondition must identify object"})
        if not case.get("oracles"):
            issues.append({"kind": "oracle", "severity": "error", "message": "at least one oracle is required"})
    errors_count = sum(item["severity"] == "error" for item in issues)
    return {"case_id": case.get("case_id", ""), "ready": errors_count == 0,
            "score": max(0, 100 - errors_count * 25 - sum(item["severity"] == "warning" for item in issues) * 5),
            "issues": issues}


def audit_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    reports = [audit_case(case) for case in cases]
    seen: set[str] = set()
    for report in reports:
        if report["case_id"] in seen:
            report["ready"] = False
            report["issues"].append({"kind": "duplicate", "severity": "error", "message": "duplicate case_id"})
        seen.add(report["case_id"])
    return {"total": len(reports), "ready": sum(item["ready"] for item in reports), "cases": reports}
