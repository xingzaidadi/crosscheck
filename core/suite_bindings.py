"""Resolve suite-local actors, fixture recipes, actions and assertion bindings."""
from __future__ import annotations

import copy
from typing import Any

from core.suite_context import SuiteContext
from core.suite_dsl import load_yaml


def resolve_bindings(case: dict[str, Any], suite: dict[str, Any], context: SuiteContext) -> dict[str, Any]:
    result = copy.deepcopy(case)
    execution = dict(result.get("execution") or {})
    connector_path = suite.get("connector")
    if not connector_path:
        return result
    connector = load_yaml(context.resolve(str(connector_path)))
    if connector.get("suite_id") != suite.get("suite_id"):
        raise ValueError("connector suite_id mismatch")

    actor = result.get("actor") or execution.pop("actor", None)
    if actor:
        actor_cfg = (connector.get("actors") or {}).get(actor)
        if not actor_cfg:
            raise ValueError(f"unknown actor: {actor}")
        if actor_cfg.get("session"):
            execution["session"] = str(context.resolve(actor_cfg["session"], allow_workspace_shared=True))

    recipe_name = execution.pop("fixture_recipe", None)
    if recipe_name:
        recipe = (connector.get("fixtures") or {}).get(recipe_name)
        if not recipe:
            raise ValueError(f"unknown fixture_recipe: {recipe_name}")
        execution.setdefault("data_prep", []).extend(copy.deepcopy(recipe.get("steps") or []))
        execution.setdefault("cleanup", []).extend(copy.deepcopy(recipe.get("cleanup") or []))
        execution.setdefault("allowed_tables", []).extend(copy.deepcopy(recipe.get("allowed_tables") or []))

    action_name = execution.pop("action_ref", None)
    if action_name:
        action = (connector.get("actions") or {}).get(action_name)
        if not action:
            raise ValueError(f"unknown action_ref: {action_name}")
        for key, value in action.items():
            execution.setdefault(key, copy.deepcopy(value))

    oracle_name = execution.pop("oracle_ref", None)
    if oracle_name:
        oracle = (connector.get("oracles") or {}).get(oracle_name)
        if not oracle:
            raise ValueError(f"unknown oracle_ref: {oracle_name}")
        execution.setdefault("engine_assertions", {}).update(copy.deepcopy(oracle.get("engine_assertions") or {}))
        execution.setdefault("assertion_bindings", {}).update(copy.deepcopy(oracle.get("assertion_bindings") or {}))

    if connector.get("base_url"):
        execution.setdefault("base_url", connector["base_url"])
    if connector.get("db"):
        execution.setdefault("db", connector["db"])
    result["execution"] = execution
    return result
