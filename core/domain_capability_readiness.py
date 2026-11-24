"""Assess whether a suite's preconditions are backed by a real capability pack.

This evaluator classifies the business actions implied by each case's
precondition text, then checks whether a validated capability pack provides a
capability of the matching kind. It never fabricates coverage: an action with
no matching healthy capability is reported as a gap.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .arsenal import load_capabilities, validate_capability_registry
from .workspace import kb_dir


# 机制层只保留"动作分类"的四个槽位与一个中性(非业务)内建兜底。
# 具体的业务触发词(例如中文流程动词)属于 workspace 资料,从
# <workspace>/knowledge_base/action_patterns.json 加载,core/ 不内置任何业务词。
# 换业务只改 workspace 的这份 JSON,core 一行不动(零业务红线)。
_DEFAULT_ACTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "create": ("draft",),
    "transition": (),
    "query": (),
    "cleanup": (),
}

_ACTION_PATTERNS_FILE = "action_patterns.json"


def load_action_patterns(kb_root: str | Path | None = None) -> dict[str, tuple[str, ...]]:
    """加载动作触发词:中性内建兜底 ∪ workspace 知识库覆盖。

    找不到 KB 文件时只返回中性内建(不含任何业务词),保证 core 可移植。"""
    patterns: dict[str, tuple[str, ...]] = {
        kind: tuple(terms) for kind, terms in _DEFAULT_ACTION_PATTERNS.items()
    }
    root = Path(kb_root) if kb_root is not None else kb_dir()
    path = root / _ACTION_PATTERNS_FILE
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = {}
        if isinstance(loaded, dict):
            for kind, terms in loaded.items():
                if kind in patterns and isinstance(terms, (list, tuple)):
                    merged = list(patterns[kind]) + [str(t) for t in terms]
                    patterns[kind] = tuple(dict.fromkeys(merged))
    return patterns

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


def required_actions(
    case: dict[str, Any], *, kb_root: str | Path | None = None
) -> list[str]:
    text = _precondition_text(case)
    if not text:
        return []
    patterns = load_action_patterns(kb_root)
    actions: list[str] = []
    for action, terms in patterns.items():
        if terms and any(term in text for term in terms):
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
