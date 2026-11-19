"""Compile approved generic rule knowledge into canonical assertion drafts."""
from __future__ import annotations

import copy
from typing import Any


def apply_rule_knowledge(case: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply explicit machine bindings only; natural-language rules never become assertions by guessing."""
    result = copy.deepcopy(case)
    execution = result.setdefault("execution", {})
    assertions = result.setdefault("assertions", {})
    bindings = execution.setdefault("assertion_bindings", {})
    engine = execution.setdefault("engine_assertions", {})
    applied = []
    for record in records:
        compiled = record.get("compiled") or {}
        for layer in ("ui", "api", "db"):
            items = compiled.get("assertions", {}).get(layer) or []
            assertions.setdefault(layer, []).extend(copy.deepcopy(items))
        for key, value in (compiled.get("engine_assertions") or {}).items():
            if key == "db":
                engine.setdefault("db", []).extend(copy.deepcopy(value or []))
            else:
                engine.setdefault(key, copy.deepcopy(value))
        bindings.update(copy.deepcopy(compiled.get("assertion_bindings") or {}))
        if compiled:
            applied.append(record["knowledge_id"])
    if applied:
        refs = list(result.get("knowledge_refs") or [])
        result["knowledge_refs"] = list(dict.fromkeys(refs + applied))
    return result
