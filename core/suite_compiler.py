"""Compile approved canonical cases into deterministic ExecSpec objects."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.spec import ExecSpec
from core.suite_context import SuiteContext
from core.suite_dsl import assertion_ids, case_content_hash, execution_id, score_case, source_hash
from core.suite_bindings import resolve_bindings


def compile_case(case: dict[str, Any], suite: dict[str, Any], context: SuiteContext) -> ExecSpec:
    original = case
    case = resolve_bindings(case, suite, context)
    connector_hash = ""
    if suite.get("connector"):
        from core.suite_dsl import load_yaml
        connector_hash = source_hash(load_yaml(context.resolve(suite["connector"])))
        if (original.get("approval") or {}).get("connector_hash") != connector_hash:
            raise ValueError("connector changed or approval.connector_hash is missing")
    if case is not original:
        case["approval"] = original.get("approval") or {}
        case_for_score = dict(case)
        case_for_score["approval"] = {"status": "human_verified", "content_hash": case_content_hash(case_for_score)}
    else:
        case_for_score = case
    original_approval = original.get("approval") or {}
    if original_approval.get("status") != "human_verified" or original_approval.get("content_hash") != case_content_hash(original):
        raise ValueError("approval must match original canonical case content_hash")
    result = score_case(case_for_score, str(suite["suite_id"]))
    if not result["execution_ready"]:
        raise ValueError(f"case is not executable: {case.get('case_id')}: {result['errors'] + result['warnings']}")
    execution = case["execution"]
    mode = execution["mode"]
    engine_assertions = execution.get("engine_assertions") or {}
    required_ids = assertion_ids(case)
    bindings = execution.get("assertion_bindings") or {}
    for assertion_id in required_ids:
        binding = bindings.get(assertion_id)
        if not isinstance(binding, dict) or not binding.get("layer") or not binding.get("proof") or not binding.get("ref"):
            raise ValueError(f"invalid assertion binding: {assertion_id}")
        _validate_binding_target(assertion_id, binding, execution)

    spec = ExecSpec(
        case_id=execution_id(case),
        title=str(case["title"]),
        level=str(case.get("priority") or ""),
        category=str(case.get("scenario_type") or ""),
        kind=str(execution.get("kind") or ("query" if mode in {"reconcile", "ui"} else "write")),
        mode=mode,
        act_via=str(execution.get("act_via") or "auto"),
        verify_status="human_verified",
        feature=str(execution.get("feature") or ""),
        db=str(execution.get("db") or (suite.get("database") or {}).get("readonly") or ""),
        base_url=str(execution.get("base_url") or suite.get("base_url") or ""),
        session=str(execution.get("session") or ""),
        request=dict(execution.get("request") or {}),
        ui=dict(execution.get("ui") or {}),
        assertions=dict(engine_assertions),
        data_prep=list(execution.get("data_prep") or []),
        steps=list(execution.get("steps") or []),
        cleanup=list(execution.get("cleanup") or (case.get("cleanup") or {}).get("targets") or []),
        allowed_tables=list(execution.get("allowed_tables") or []),
        mapping=_resolve_optional(context, execution.get("mapping")),
        sample=_resolve_optional(context, execution.get("sample")),
        marker_field=str(execution.get("marker_field") or ""),
        code_path=str(execution.get("code_path") or ""),
        approve=dict(execution.get("approve") or {}),
        verify_poll=dict(execution.get("verify_poll") or {}),
        prepare_state=str(execution.get("prepare_state") or ""),
        blocked="",
        needs_review=[],
        raw={
            "canonical_case_id": case["case_id"],
            "suite_id": suite["suite_id"],
            "suite_hash": source_hash(suite),
            "case_hash": case_content_hash(original),
            "connector_hash": connector_hash,
            "assertion_ids": required_ids,
            "assertion_bindings": bindings,
        },
    )
    _validate_compiled(spec, case)
    return spec


def compile_suite(suite: dict[str, Any], cases: list[dict[str, Any]], context: SuiteContext) -> tuple[list[ExecSpec], list[dict]]:
    specs: list[ExecSpec] = []
    invalid: list[dict] = []
    for case in cases:
        if case.get("status") != "ready":
            continue
        try:
            specs.append(compile_case(case, suite, context))
        except Exception as exc:  # noqa: BLE001
            invalid.append({"case_id": case.get("case_id", ""), "error": str(exc)})
    return specs, invalid


def plan_hash(specs: list[ExecSpec]) -> str:
    payload = [asdict(spec) for spec in specs]
    return source_hash({"specs": payload})


def write_plan(specs: list[ExecSpec], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"plan_hash": plan_hash(specs), "specs": [asdict(spec) for spec in specs]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _resolve_optional(context: SuiteContext, value: Any) -> str:
    if not value:
        return ""
    return str(context.resolve(str(value)))


def _validate_compiled(spec: ExecSpec, case: dict[str, Any]) -> None:
    required_layers = set((case.get("layers") or {}).get("required") or [])
    if "ui" in required_layers and spec.mode != "ui":
        raise ValueError("UI is required but execution.mode is not ui")
    if "api" in required_layers and not (spec.request or (spec.ui or {}).get("url_pattern") or spec.mode == "reconcile"):
        raise ValueError("API is required but no request/url_pattern is bound")
    if "db" in required_layers and not ((spec.assertions or {}).get("db") or spec.mapping):
        raise ValueError("DB is required but no DB assertion/mapping is bound")
    if spec.mode in {"api", "write"} and (not spec.cleanup or not spec.allowed_tables):
        raise ValueError("write execution requires cleanup and allowed_tables")


def _validate_binding_target(assertion_id: str, binding: dict, execution: dict) -> None:
    proof, ref = binding["proof"], str(binding["ref"])
    if proof == "api_response" and ref != "engine_assertions.response":
        raise ValueError(f"{assertion_id}: api_response must bind engine_assertions.response")
    if proof == "api_response" and not (execution.get("engine_assertions") or {}).get("response"):
        raise ValueError(f"{assertion_id}: response assertion does not exist")
    if proof == "db_assertion":
        if not ref.startswith("engine_assertions.db["):
            raise ValueError(f"{assertion_id}: db_assertion must bind engine_assertions.db[index]")
        try:
            index = int(ref.removeprefix("engine_assertions.db[").removesuffix("]"))
            (execution.get("engine_assertions") or {}).get("db", [])[index]
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{assertion_id}: DB assertion ref does not exist: {ref}") from exc
    if proof == "ui_check" and ref not in {"ui.extract", "ui.value_asserts", "ui.visibility_asserts", "ui.field_asserts"}:
        raise ValueError(f"{assertion_id}: unsupported UI proof ref: {ref}")
    if proof == "ui_check" and not (execution.get("ui") or {}).get(ref.split(".")[1]):
        raise ValueError(f"{assertion_id}: UI oracle does not exist: {ref}")
    if proof == "reconcile" and ref != "mapping":
        raise ValueError(f"{assertion_id}: reconcile must bind mapping")
    if proof == "reconcile" and not execution.get("mapping"):
        raise ValueError(f"{assertion_id}: suite-local mapping is required")
    if proof in {"event", "script"}:
        raise ValueError(f"{assertion_id}: canonical proof executor is not implemented: {proof}")
