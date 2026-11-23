"""Unified business complexity and automation readiness assessment.

This module deliberately scores evidence that is present in a suite or run
report. It never treats an absent signal as a passing result.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .precondition_readiness import assess_preconditions
from .oracle_readiness import assess_oracles

COMPLEXITY_ORDER = ("L0", "L1", "L2", "L3", "L4")
MATURITY_ORDER = ("M0", "M1", "M2", "M3", "M4")


def _items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", {}):
        return []
    return [value]


def _required_layers(case: dict[str, Any]) -> set[str]:
    layers = case.get("layers") or {}
    if not isinstance(layers, dict):
        return set()
    return {str(layer) for layer in _items(layers.get("required")) if layer}


def _case_text(case: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("title", "scenario_type", "business_tags", "intent", "notes", "action", "preconditions"):
        value = case.get(key)
        if isinstance(value, (dict, list)):
            values.append(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
        elif value not in (None, ""):
            values.append(str(value))
    return " ".join(values).lower()


def assess_case_complexity(case: dict[str, Any]) -> dict[str, Any]:
    """Return a transparent complexity assessment for one canonical case."""
    layers = _required_layers(case)
    execution = case.get("execution") or {}
    if not isinstance(execution, dict):
        execution = {}
    preconditions = _items(case.get("preconditions")) + _items(case.get("data"))
    preconditions += _items(execution.get("prepare_state")) + _items(execution.get("fixture_recipe"))
    assertions = case.get("assertions") or {}
    if not isinstance(assertions, dict):
        assertions = {}
    events_required = "event" in layers or bool(_items(assertions.get("event")))
    wait_required = bool(case.get("wait")) or bool(execution.get("verify_poll"))
    text = _case_text(case)
    workflow_terms = ("审批", "退款", "订单", "状态", "提交", "发布", "签署", "流转", "workflow", "refund")
    high_risk_terms = ("支付系统", "清算", "财务", "权限", "幂等", "并发", "核心交易", "payment_gateway", "settlement_risk")
    state_dependency = bool(preconditions) or any(term in text for term in workflow_terms)
    high_risk = any(term in text for term in high_risk_terms)
    cross_system = len(layers & {"ui", "api", "db", "event"}) >= 3 or events_required

    dimensions = {
        "layer_count": len(layers),
        "state_dependency": state_dependency,
        "cross_system": cross_system,
        "async_dependency": wait_required or events_required,
        "high_risk": high_risk,
        "precondition_count": len(preconditions),
    }
    if high_risk and (cross_system or state_dependency):
        level = "L4"
    elif cross_system and state_dependency:
        level = "L3"
    elif state_dependency or len(layers) >= 2:
        level = "L2"
    elif layers or case.get("actions") or case.get("action"):
        level = "L1"
    else:
        level = "L0"
    return {"case_id": case.get("case_id", ""), "level": level, "dimensions": dimensions}


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _run_metrics(run_report: dict[str, Any] | None) -> dict[str, float]:
    if not run_report:
        return {"run_stability": 0.0, "inconclusive_rate": 1.0, "has_run_evidence": 0.0}
    total = int(run_report.get("total") or 0)
    passed = int(run_report.get("passed", run_report.get("pass", 0)) or 0)
    inconclusive = int(run_report.get("inconclusive") or 0)
    soak_runs = int(run_report.get("soak_runs") or 0)
    if total <= 0 and isinstance(run_report.get("cases"), list):
        case_results = run_report["cases"]
        total = len(case_results)
        passed = sum(item.get("status") in {"PASS", "PASSED", "passed"} for item in case_results if isinstance(item, dict))
        inconclusive = sum(item.get("status") in {"INCONCLUSIVE", "unknown", "UNKNOWN"} for item in case_results if isinstance(item, dict))
    stability = _ratio(passed, total)
    if soak_runs >= 5 and stability >= 0.95:
        stability = min(1.0, stability + 0.05)
    return {"run_stability": stability, "inconclusive_rate": _ratio(inconclusive, total),
            "has_run_evidence": 1.0 if total else 0.0}


def assess_product_readiness(
    suite: dict[str, Any],
    cases: list[dict[str, Any]],
    *,
    run_report: dict[str, Any] | None = None,
    suite_dir: str | Path | None = None,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    """Assess complexity, maturity, production readiness and next actions."""
    total = len(cases)
    complexity_items = [assess_case_complexity(case) for case in cases]
    level_index = max((COMPLEXITY_ORDER.index(item["level"]) for item in complexity_items), default=0)
    complexity_level = COMPLEXITY_ORDER[level_index]

    ready_count = sum(str(case.get("status", "")).lower() == "ready" for case in cases)
    approved_count = sum(bool((case.get("approval") or {}).get("approved_at")) or bool((case.get("approval") or {}).get("reviewer"))
                         for case in cases if isinstance(case.get("approval"), dict))
    executable_count = sum(bool(case.get("execution")) for case in cases)
    evidence_count = 0
    cleanup_count = 0
    for case in cases:
        evidence = case.get("evidence") or {}
        assertions = case.get("assertions") or {}
        if evidence or assertions:
            evidence_count += 1
        execution = case.get("execution") or {}
        mutating = str(execution.get("mode", "")).lower() in {"write", "api"} or bool(execution.get("cleanup"))
        if not mutating or execution.get("cleanup"):
            cleanup_count += 1

    run_metrics = _run_metrics(run_report)
    preparation = assess_preconditions(cases, suite_dir=suite_dir, workspace=workspace)
    oracle_readiness = assess_oracles(cases, suite_dir=str(suite_dir) if suite_dir else None)
    dimensions = {
        "readiness": _ratio(ready_count, total),
        "approval": _ratio(approved_count, total),
        "execution_binding": _ratio(executable_count, total),
        "evidence": _ratio(evidence_count, total),
        "oracle": oracle_readiness["coverage"],
        "cleanup": _ratio(cleanup_count, total),
        "preparation": preparation["coverage"],
        **run_metrics,
    }
    score = round((dimensions["readiness"] * 0.18
                   + dimensions["approval"] * 0.09
                   + dimensions["execution_binding"] * 0.14
                   + dimensions["evidence"] * 0.10
                   + dimensions["oracle"] * 0.14
                   + dimensions["cleanup"] * 0.10
                   + dimensions["preparation"] * 0.15
                   + dimensions["run_stability"] * 0.10) * 100, 1)
    if score >= 95 and dimensions["has_run_evidence"]:
        maturity_level = "M4"
    elif score >= 75 and dimensions["has_run_evidence"]:
        maturity_level = "M3"
    elif score >= 50:
        maturity_level = "M2"
    elif score > 0:
        maturity_level = "M1"
    else:
        maturity_level = "M0"

    blockers: list[dict[str, Any]] = []
    if dimensions["readiness"] < 1:
        blockers.append({"type": "readiness_blocked", "count": total - ready_count,
                         "action": "补齐用例 schema、路由、断言和审批，直到用例进入 READY"})
    if dimensions["approval"] < dimensions["readiness"]:
        blockers.append({"type": "governance_blocked", "count": max(0, ready_count - approved_count),
                         "action": "为正式用例补充知识引用、审批人和内容 hash"})
    if dimensions["execution_binding"] < dimensions["readiness"]:
        blockers.append({"type": "asset_blocked", "count": max(0, ready_count - executable_count),
                         "action": "补充 UI/API/DB 绑定或对应的 capability pack"})
    if dimensions["evidence"] < 1:
        blockers.append({"type": "oracle_blocked", "count": total - evidence_count,
                         "action": "为每条关键用例配置业务 Oracle 和至少一类可复核证据"})
    if oracle_readiness["blocked"] or oracle_readiness["partial"]:
        blockers.append({"type": "oracle_blocked", "count": oracle_readiness["blocked"] + oracle_readiness["partial"],
                         "action": "将自然语言期望拆成结构化业务 Oracle，并绑定 UI/API/DB/Event/Log 证明来源"})
    if dimensions["cleanup"] < 1:
        blockers.append({"type": "data_blocked", "count": total - cleanup_count,
                         "action": "补充测试数据标记、清理或补偿策略"})
    if preparation["blocked"]:
        blockers.append({"type": "state_blocked", "count": preparation["blocked"],
                         "action": "为声明了前置条件但没有可执行来源的用例补充 fixture、state recipe 或 capability pack"})
    if not run_report:
        blockers.append({"type": "external_evidence_missing", "count": 1,
                         "action": "执行 pilot 和连续 soak，证明无人值守稳定性"})
    elif dimensions["inconclusive_rate"] > 0.10:
        blockers.append({"type": "evidence_blocked", "count": 1,
                         "action": "降低 INCONCLUSIVE 比例并补齐跨层或异步证据"})

    return {
        "schema_version": 1,
        "suite_id": suite.get("suite_id", ""),
        "total_cases": total,
        "complexity": {"level": complexity_level, "distribution": {
            level: sum(item["level"] == level for item in complexity_items) for level in COMPLEXITY_ORDER
        }, "cases": complexity_items},
        "maturity": {"level": maturity_level, "score": score, "dimensions": dimensions},
        "production_readiness": "READY" if maturity_level in {"M3", "M4"} and not blockers else "NOT_READY",
        "preparation": preparation,
        "oracle_readiness": oracle_readiness,
        "blockers": blockers,
        "next_actions": [item["action"] for item in blockers[:5]],
    }


def write_product_readiness(report: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
