"""Adapt approved remediation assets into the existing deterministic executor."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .approved_assets import load_approved_assets


def _json_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _case_key(case: dict[str, Any]) -> str:
    source = case.get("source") or {}
    return str(source.get("case_key") or case.get("case_id") or "") if isinstance(source, dict) else str(case.get("case_id") or "")


def _fixture_for_case(suite_dir: str | Path, case: dict[str, Any]) -> dict[str, Any] | None:
    key = _case_key(case)
    for fixture in load_approved_assets(suite_dir, "fixtures"):
        if key in set(fixture.get("case_keys") or []):
            return fixture
    return None


def _oracle_for_case(suite_dir: str | Path, case: dict[str, Any]) -> dict[str, Any] | None:
    case_id = str(case.get("case_id") or "")
    for oracle in load_approved_assets(suite_dir, "oracles"):
        if str(oracle.get("case_id") or "") == case_id:
            return oracle
    return None


def _merge_steps(existing: list[Any], additions: list[Any]) -> list[Any]:
    result = list(existing)
    seen = {_json_key(item) for item in result}
    for item in additions:
        if _json_key(item) not in seen:
            result.append(copy.deepcopy(item))
            seen.add(_json_key(item))
    return result


def _api_assertion(item: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    identifier = str(item.get("id") or "")
    subject = str(item.get("subject") or "")
    operator = str(item.get("operator") or "equals")
    if not identifier or operator != "equals" or "expected" not in item:
        return None
    normalized = subject.lower().replace(" ", "")
    if normalized in {"status", "http.status", "response.status", "api.status"}:
        return identifier, {"status": item["expected"]}
    for prefix in ("response.body.", "body.", "response."):
        if subject.startswith(prefix):
            path = subject[len(prefix):]
            if path:
                return identifier, {"body": {path: item["expected"]}}
    return None


def _db_assertion(item: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    identifier = str(item.get("id") or "")
    if not identifier or "expected" not in item:
        return None
    table = str(item.get("table") or "")
    where = str(item.get("where") or "")
    if not table or not where:
        return None
    expected = item.get("expected")
    result = {"table": table, "where": where}
    if isinstance(expected, dict):
        for key in ("row_count", "row_count_min", "fields", "db"):
            if key in expected:
                result[key] = expected[key]
    elif isinstance(expected, int):
        result["row_count"] = expected
    else:
        return None
    return identifier, result


def inject_approved_assets(case: dict[str, Any], suite_dir: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a copy of *case* with executable approved assets injected.

    The returned metadata records injected asset hashes and unsupported oracle
    items. Unsupported items are not silently treated as executable.
    """
    result = copy.deepcopy(case)
    execution = result.setdefault("execution", {})
    metadata: dict[str, Any] = {"fixture": None, "oracle": None, "unsupported_oracles": []}

    fixture = _fixture_for_case(suite_dir, result)
    if fixture:
        steps = fixture.get("steps") or []
        execution["data_prep"] = _merge_steps(execution.get("data_prep") or [], steps)
        metadata["fixture"] = {
            "asset_id": fixture.get("fixture_id"),
            "content_hash": fixture.get("content_hash"),
            "steps": len(steps),
        }

    oracle = _oracle_for_case(suite_dir, result)
    if oracle:
        metadata["oracle"] = {
            "asset_id": oracle.get("oracle_id"),
            "content_hash": oracle.get("content_hash"),
        }
        engine = execution.setdefault("engine_assertions", {})
        bindings = execution.setdefault("assertion_bindings", {})
        case_assertions = result.setdefault("assertions", {})
        for item in oracle.get("assertions") or []:
            if not isinstance(item, dict):
                metadata["unsupported_oracles"].append({"item": item, "reason": "not an object"})
                continue
            proof = str(item.get("proof") or item.get("kind") or "").lower()
            converted = _api_assertion(item) if proof in {"api", "api_response"} else None
            layer = "api"
            if proof in {"db", "db_assertion", "reconcile"}:
                converted = _db_assertion(item)
                layer = "db"
            if converted is None:
                metadata["unsupported_oracles"].append({"id": item.get("id"), "proof": proof,
                                                        "reason": "not supported by current ExecSpec executor"})
                continue
            identifier, assertion = converted
            if layer == "api":
                response = dict(engine.get("response") or {})
                response.update(assertion)
                engine["response"] = response
                case_assertions.setdefault("api", []).append({"id": identifier, "proof": "api_response",
                                                               "subject": item.get("subject"),
                                                               "operator": item.get("operator", "equals"),
                                                               "expected": item.get("expected")})
                bindings[identifier] = {"layer": "api", "proof": "api_response",
                                        "ref": "engine_assertions.response"}
            else:
                db_assertions = list(engine.get("db") or [])
                db_index = len(db_assertions)
                db_assertions.append(assertion)
                engine["db"] = db_assertions
                case_assertions.setdefault("db", []).append({"id": identifier, "proof": "db_assertion",
                                                               "table": assertion["table"],
                                                               "where": assertion["where"],
                                                               "expected": item.get("expected")})
                bindings[identifier] = {"layer": "db", "proof": "db_assertion",
                                        "ref": f"engine_assertions.db[{db_index}]"}

    return result, metadata
