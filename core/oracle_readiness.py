"""Audit business-oracle declarations before a case is executed.

Execution-time truth lives in :mod:`core.oracle`.  This module only audits the
case contract: whether the expected business result is structured, tied to a
proof source, and accompanied by the evidence layers it needs.
"""
from __future__ import annotations

from typing import Any

from .approved_assets import approved_oracle_for_case


EVIDENCE_ALIASES = {
    "screenshot": "ui",
    "ui": "ui",
    "ui_check": "ui",
    "api_request": "api",
    "api_response": "api",
    "api": "api",
    "db_result": "db",
    "db_assertion": "db",
    "db": "db",
    "event": "event",
    "message": "event",
    "log": "log",
    "audit_log": "log",
}

PROOF_ALIASES = {
    "ui_check": "ui",
    "ui": "ui",
    "api_response": "api",
    "api": "api",
    "db_assertion": "db",
    "db": "db",
    "reconcile": "db",
    "event": "event",
    "script": "script",
}


def _items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", {}):
        return []
    return [value]


def _structured_assertions(case: dict[str, Any]) -> list[dict[str, Any]]:
    assertions = case.get("assertions") or {}
    if not isinstance(assertions, dict):
        assertions = {}
    result: list[dict[str, Any]] = []
    for layer, values in assertions.items():
        if layer in {"source_text", "business_text"}:
            continue
        for value in _items(values):
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("layer", str(layer))
                result.append(item)
    for value in _items(case.get("oracles")) + _items(case.get("business_oracle")):
        if isinstance(value, dict):
            result.append(dict(value))
    return result


def _proof_layer(item: dict[str, Any]) -> str | None:
    proof = item.get("proof") or item.get("kind") or item.get("layer")
    if isinstance(proof, dict):
        proof = proof.get("type") or proof.get("kind")
    return PROOF_ALIASES.get(str(proof or "").lower())


def _required_evidence(case: dict[str, Any]) -> list[str]:
    evidence = case.get("evidence") or {}
    if isinstance(evidence, dict):
        values = evidence.get("required") or evidence.get("layers") or []
    else:
        values = evidence
    return [str(value) for value in _items(values) if value]


def assess_case_oracles(case: dict[str, Any], *, suite_dir: str | None = None) -> dict[str, Any]:
    assertions = _structured_assertions(case)
    approved = approved_oracle_for_case(suite_dir, str(case.get("case_id") or ""))
    if approved:
        assertions.extend(_items(approved.get("assertions")))
    required_evidence = _required_evidence(case)
    required_layers = {EVIDENCE_ALIASES.get(value.lower(), value.lower()) for value in required_evidence}
    proof_layers = {layer for item in assertions if (layer := _proof_layer(item))}
    unbound = [str(item.get("id") or item.get("name") or "<unnamed>")
               for item in assertions if not _proof_layer(item)]
    missing_evidence = sorted(required_layers - proof_layers)
    if not assertions:
        status = "blocked"
        reason = "没有结构化业务 Oracle；只有自然语言期望无法作为确定性判定"
    elif unbound:
        status = "partial"
        reason = "存在未绑定证明来源的断言"
    elif missing_evidence:
        status = "partial"
        reason = "声明的证据层没有对应 Oracle 证明"
    else:
        status = "ready"
        reason = "结构化 Oracle 已绑定证明来源，且证据声明可覆盖"
    return {
        "case_id": case.get("case_id", ""),
        "status": status,
        "reason": reason,
        "oracle_count": len(assertions),
        "proof_layers": sorted(proof_layers),
        "required_evidence": required_evidence,
        "missing_evidence": missing_evidence,
        "unbound_oracles": unbound,
    }


def assess_oracles(cases: list[dict[str, Any]], *, suite_dir: str | None = None) -> dict[str, Any]:
    results = [assess_case_oracles(case, suite_dir=suite_dir) for case in cases]
    ready = sum(item["status"] == "ready" for item in results)
    partial = sum(item["status"] == "partial" for item in results)
    blocked = sum(item["status"] == "blocked" for item in results)
    return {
        "total": len(results),
        "ready": ready,
        "partial": partial,
        "blocked": blocked,
        "coverage": round(ready / len(results), 4) if results else 0.0,
        "cases": results,
    }
