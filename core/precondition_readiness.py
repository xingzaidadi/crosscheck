"""Assess whether case preconditions can be prepared safely and repeatably."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .arsenal import load_capabilities, plan_dependencies
from .approved_assets import approved_fixture_for_case
from .fixture_registry import fixture_for_case, load_registry
from .state_recipe import recipe_steps


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", {}):
        return []
    return [value]


def _case_key(case: dict[str, Any]) -> str:
    source = case.get("source") or {}
    if isinstance(source, dict) and source.get("case_key"):
        return str(source["case_key"])
    return str(case.get("case_id") or "")


def _precondition_text(case: dict[str, Any]) -> str:
    data = case.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    values = [case.get("preconditions"), data.get("preconditions_text"), case.get("notes")]
    return " ".join(str(value) for value in values if value not in (None, "", [], {})).strip()


def _recipe_candidates(case: dict[str, Any]) -> list[dict[str, str]]:
    execution = case.get("execution") or {}
    if not isinstance(execution, dict):
        execution = {}
    candidates: list[dict[str, str]] = []
    for value in (execution.get("prepare_state"), execution.get("fixture_recipe"), case.get("state_recipe")):
        for item in _list(value):
            if isinstance(item, dict):
                feature = str(item.get("feature") or item.get("domain") or execution.get("feature") or "")
                state = str(item.get("state") or item.get("target_state") or "")
            else:
                feature = str(execution.get("feature") or "")
                state = str(item or "")
            if feature and state:
                candidates.append({"feature": feature, "state": state})
    return candidates


def _capability_request(case: dict[str, Any]) -> bool:
    action = case.get("action") or {}
    if isinstance(action, dict) and action.get("capability"):
        return True
    for item in _list(case.get("preconditions")):
        if isinstance(item, dict) and item.get("capability"):
            return True
    return False


def assess_case_preconditions(
    case: dict[str, Any],
    *,
    suite_dir: str | Path | None = None,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    """Return an evidence-bound preparation status for one case."""
    suite_root = Path(suite_dir) if suite_dir else None
    workspace_root = Path(workspace) if workspace else None
    case_key = _case_key(case)
    text = _precondition_text(case)
    registry = load_registry(suite_root) if suite_root else {"fixtures": {}}
    fixture = fixture_for_case(registry, case_key)
    if fixture is None:
        fixture = approved_fixture_for_case(suite_root, case_key)
    signals: list[dict[str, Any]] = []

    if fixture:
        signals.append({"kind": "fixture", "name": fixture.get("name") or fixture.get("fixture_id") or case_key,
                        "verified": bool(fixture.get("verified")),
                        "source": "approved_assets" if fixture.get("status") == "approved" else "suite/fixtures.yaml"})

    recipes_dir = workspace_root / "knowledge_base" / "state_recipes" if workspace_root else None
    for candidate in _recipe_candidates(case):
        steps = recipe_steps(candidate["feature"], candidate["state"], recipes_dir=recipes_dir)
        signals.append({"kind": "state_recipe", **candidate, "steps": len(steps),
                        "verified": bool(steps), "source": "knowledge_base/state_recipes"})

    capability_result: dict[str, Any] | None = None
    if _capability_request(case) and workspace_root:
        registry_path = workspace_root / "config" / "capabilities.yaml"
        if registry_path.exists():
            try:
                capabilities = load_capabilities(registry_path)
                environment = str((case.get("environment") or "unknown")).lower()
                plan = plan_dependencies(case, capabilities, environment=environment, run_id="readiness")
                capability_result = {"verified": True, "steps": len(plan.steps),
                                     "plan_hash": plan.plan_hash, "source": str(registry_path)}
            except (OSError, ValueError, KeyError) as exc:
                capability_result = {"verified": False, "error": str(exc),
                                     "source": str(registry_path)}
        else:
            capability_result = {"verified": False, "error": "capability registry missing",
                                 "source": str(registry_path)}
        signals.append({"kind": "capability_plan", **capability_result})

    required = bool(text)
    if not required:
        status = "not_required"
        reason = "未声明前置条件"
    elif any(item.get("verified") for item in signals):
        status = "ready"
        reason = "存在已验证的 fixture、state recipe 或 capability plan"
    else:
        status = "blocked"
        reason = "已声明前置条件，但没有可执行且已验证的准备来源"
    return {"case_id": case.get("case_id", ""), "case_key": case_key,
            "status": status, "reason": reason,
            "declared": required, "signals": signals}


def assess_preconditions(
    cases: list[dict[str, Any]],
    *,
    suite_dir: str | Path | None = None,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    results = [assess_case_preconditions(case, suite_dir=suite_dir, workspace=workspace) for case in cases]
    declared = [item for item in results if item["declared"]]
    ready = [item for item in declared if item["status"] == "ready"]
    blocked = [item for item in declared if item["status"] == "blocked"]
    return {
        "total": len(results), "declared": len(declared), "ready": len(ready), "blocked": len(blocked),
        "coverage": round(len(ready) / len(declared), 4) if declared else 1.0,
        "cases": results,
    }
