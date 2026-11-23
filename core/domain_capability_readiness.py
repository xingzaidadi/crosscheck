"""Assess whether a suite's preconditions are backed by a real capability pack.

This evaluator classifies the business actions implied by each case's
precondition text, then checks whether a validated capability pack provides a
capability of the matching kind. It never fabricates coverage: an action with
no matching healthy capability is reported as a gap.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .arsenal import load_capabilities, validate_capability_registry


ACTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "create": ("创建", "新建", "构造", "准备", "生成", "存在", "含", "草稿", "draft"),
    "transition": ("提交", "审批", "发策略", "发招采", "签合同", "下单", "下订单", "受理",
                   "转办", "退回", "撤回", "关闭", "完成", "状态", "流转", "回写", "占用"),
    "query": ("查询", "列表", "检索", "展示", "页签", "筛选", "分页", "字段"),
    "cleanup": ("清理", "删除", "作废", "回收", "补偿"),
}

KIND_ALIASES = {
    "create": {"create"},
    "transition": {"transition", "maintain"},
    "query": {"find", "query"},
    "cleanup": {"compensate", "cleanup"},
}


def _precondition_text(case: dict[str, Any]) -> str:
    data = case.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    parts = [case.get("preconditions"), data.get("preconditions_text"), case.get("notes")]
    return " ".join(str(part) for part in parts if part not in (None, "", [], {})).strip()


def required_actions(case: dict[str, Any]) -> list[str]:
    text = _precondition_text(case)
    if not text:
        return []
    actions: list[str] = []
    for action, terms in ACTION_PATTERNS.items():
        if any(term in text for term in terms):
            actions.append(action)
    return actions


def _provided_kinds(capabilities: list[Any]) -> set[str]:
    return {str(getattr(capability, "kind", "")).lower() for capability in capabilities}


def assess_domain_capabilities(
    cases: list[dict[str, Any]],
    *,
    registry_path: str | Path,
    environment: str = "test",
) -> dict[str, Any]:
    """Classify required business actions and check capability-pack coverage."""
    registry = Path(registry_path)
    pack_errors: list[str] = []
    provided: set[str] = set()
    pack_available = registry.is_file()
    if pack_available:
        capabilities = load_capabilities(registry)
        pack_errors = validate_capability_registry(capabilities, environment=environment)
        provided = _provided_kinds(capabilities)

    action_counts: dict[str, int] = {}
    covered_counts: dict[str, int] = {}
    case_rows: list[dict[str, Any]] = []
    for case in cases:
        actions = required_actions(case)
        covered: list[str] = []
        missing: list[str] = []
        for action in actions:
            action_counts[action] = action_counts.get(action, 0) + 1
            if pack_available and not pack_errors and (KIND_ALIASES[action] & provided):
                covered.append(action)
                covered_counts[action] = covered_counts.get(action, 0) + 1
            else:
                missing.append(action)
        case_rows.append({
            "case_id": case.get("case_id", ""),
            "required_actions": actions,
            "covered_actions": covered,
            "missing_actions": missing,
            "status": "ready" if actions and not missing else ("not_required" if not actions else "gap"),
        })

    total_actions = sum(action_counts.values())
    covered_actions = sum(covered_counts.values())
    gaps = sorted({action for row in case_rows for action in row["missing_actions"]})
    return {
        "schema_version": 1,
        "environment": environment,
        "registry": str(registry),
        "capability_pack_available": pack_available,
        "capability_pack_valid": pack_available and not pack_errors,
        "capability_pack_errors": pack_errors,
        "provided_kinds": sorted(provided),
        "action_counts": action_counts,
        "covered_counts": covered_counts,
        "coverage": round(covered_actions / total_actions, 4) if total_actions else 1.0,
        "missing_action_kinds": gaps,
        "cases": case_rows,
    }
