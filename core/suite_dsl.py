"""Canonical suite DSL: validate, score, and compile structured cases."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


LAYERS = {"ui", "api", "db", "manual", "script"}
REQUIRED_CASE_KEYS = {"case_id", "title", "suite_id", "status", "layers", "assertions"}
ALLOWED_CASE_KEYS = {
    "schema_version", "case_id", "title", "suite_id", "version", "source", "priority", "status",
    "scenario_type", "business_tags", "layers", "actors", "data", "actions", "assertions", "cleanup",
    "evidence", "approval", "execution", "notes", "open_questions",
    "actor",
}
ALLOWED_EXECUTION_KEYS = {
    "mode", "kind", "act_via", "feature", "db", "base_url", "session", "request", "ui",
    "engine_assertions", "data_prep", "steps", "cleanup", "allowed_tables", "mapping", "sample",
    "marker_field", "code_path", "approve", "verify_poll", "prepare_state", "assertion_bindings",
    "actor", "fixture_recipe", "action_ref", "oracle_ref",
}
PROOF_TYPES = {"ui_check", "api_response", "db_assertion", "reconcile", "event", "script"}
SCHEMA_VERSION = 1
CASE_STATUSES = {"draft", "ready", "blocked"}
EXEC_MODES = {"reconcile", "api", "write", "ui", "script"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


def load_yaml(path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return data


def suite_id(data: dict[str, Any]) -> str:
    value = str(data.get("suite_id") or "").strip()
    if not value:
        raise ValueError("suite_id is required")
    return value


def validate_suite(data: dict[str, Any]) -> list[str]:
    errors = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"suite schema_version must be {SCHEMA_VERSION}")
    try:
        suite_id(data)
    except ValueError as exc:
        errors.append(str(exc))
    environment = str(data.get("environment") or "unknown").lower()
    if environment in {"prod", "production", "生产"}:
        errors.append("production environment is forbidden")
    return errors


def source_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def case_content_hash(case: dict[str, Any]) -> str:
    clean = {key: value for key, value in case.items() if key not in {"approval", "compiled"}}
    return source_hash(clean)


def execution_id(case: dict[str, Any]) -> str:
    sid = re.sub(r"[^A-Za-z0-9._-]+", "-", str(case.get("suite_id") or "suite")).strip("-")
    key = re.sub(r"[^A-Za-z0-9._-]+", "-", str((case.get("source") or {}).get("case_key") or "case")).strip("-")
    return f"{sid}__{key}__{case_content_hash(case)[:8]}"


def assertion_ids(case: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for layer, items in (case.get("assertions") or {}).items():
        if layer == "source_text" or not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))
    return ids


def _layers(case: dict[str, Any]) -> tuple[set[str], list[str]]:
    layers = case.get("layers") or {}
    required = set(layers.get("required") or [])
    errors = [f"unsupported layer: {value}" for value in required - LAYERS]
    return required, errors


def score_case(case: dict[str, Any], expected_suite: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    missing = sorted(REQUIRED_CASE_KEYS - set(case))
    errors.extend(f"missing key: {key}" for key in missing)
    errors.extend(f"unknown key: {key}" for key in sorted(set(case) - ALLOWED_CASE_KEYS))
    case_suite = str(case.get("suite_id") or "")
    if case.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not _SAFE_ID.fullmatch(str(case.get("case_id") or "")):
        errors.append("case_id is missing or unsafe")
    if case.get("status") not in CASE_STATUSES:
        errors.append(f"unsupported status: {case.get('status')!r}")
    if expected_suite and case_suite != expected_suite:
        errors.append(f"suite mismatch: {case_suite!r} != {expected_suite!r}")
    required, layer_errors = _layers(case)
    errors.extend(layer_errors)
    assertions = case.get("assertions") or {}
    for layer in required - {"manual", "script"}:
        if not assertions.get(layer):
            warnings.append(f"missing {layer} assertions")
    if required and not (case.get("actions") or case.get("data")):
        warnings.append("missing actions/data preparation")
    if required & {"ui", "api", "db"} and not case.get("cleanup"):
        warnings.append("missing cleanup")
    if case.get("status") == "ready" and (errors or warnings):
        errors.append("ready case is incomplete")
    if case.get("status") == "ready":
        approval = case.get("approval") or {}
        expected_hash = case_content_hash(case)
        if approval.get("status") != "human_verified" or approval.get("content_hash") != expected_hash:
            errors.append("ready case requires human_verified approval bound to current content_hash")
        execution = case.get("execution") or {}
        errors.extend(f"unknown execution key: {key}" for key in sorted(set(execution) - ALLOWED_EXECUTION_KEYS))
        if execution.get("mode") not in EXEC_MODES:
            errors.append("ready case requires a supported execution.mode")
        ids = assertion_ids(case)
        if not ids:
            errors.append("ready case requires assertion IDs")
        bound = set((execution.get("assertion_bindings") or {}).keys())
        missing_bindings = sorted(set(ids) - bound)
        if missing_bindings:
            errors.append(f"unbound assertions: {missing_bindings}")
        for assertion_id, binding in (execution.get("assertion_bindings") or {}).items():
            if not isinstance(binding, dict) or binding.get("proof") not in PROOF_TYPES:
                errors.append(f"assertion {assertion_id} requires proof in {sorted(PROOF_TYPES)}")
            elif not binding.get("ref"):
                errors.append(f"assertion {assertion_id} requires a concrete proof ref")
    score = 0
    score += 10 if case.get("case_id") and case.get("title") and case.get("suite_id") else 0
    score += 10 if case.get("source") else 0
    score += 10 if required else 0
    score += 15 if (case.get("data") or {}).get("fixtures") else 0
    actions = case.get("actions") or {}
    score += 15 if any(actions.get(layer) for layer in required & {"ui", "api", "db"}) else 0
    score += sum(10 for layer in required & {"ui", "api", "db"} if assertions.get(layer))
    score += 10 if case.get("cleanup") and (case.get("cleanup") or {}).get("targets") else 0
    score += 10 if (case.get("evidence") or {}).get("required") else 0
    score -= len(errors) * 20
    score = max(0, score)
    return {"case_id": case.get("case_id", ""), "content_hash": case_content_hash(case),
            "score": min(100, score), "errors": errors,
            "warnings": warnings,
            "schema_valid": not errors,
            "execution_ready": case.get("status") == "ready" and not errors and not warnings}


def score_suite(suite: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    sid = suite_id(suite)
    suite_errors = validate_suite(suite)
    results = [score_case(case, sid) for case in cases]
    total = len(results)
    average = round(sum(item["score"] for item in results) / total, 1) if total else 0
    return {
        "suite_id": sid, "suite_hash": source_hash(suite), "total": total,
        "schema_valid": sum(item["schema_valid"] for item in results),
        "execution_ready": sum(item["execution_ready"] for item in results), "average_score": average,
        "suite_errors": suite_errors, "results": results,
    }


def load_suite(directory: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = Path(directory)
    suite = load_yaml(root / "suite.yaml")
    errors = validate_suite(suite)
    if errors:
        raise ValueError(f"invalid suite: {errors}")
    cases = [load_yaml(path) for path in sorted((root / "cases").glob("*.yaml"))]
    ids = [str(case.get("case_id") or "") for case in cases]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate case_id: {duplicates}")
    return suite, cases


def write_score(score: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
