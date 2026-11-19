"""Validate and apply reviewed onboarding gap resolutions as configuration assets."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from core.framework import GAP_TYPES, fingerprint

RESOLUTION_TYPES = {"binding", "oracle", "fixture", "environment", "business_input", "manual"}


def load_resolutions(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {"schema_version": 1, "resolutions": []}
    target = Path(path)
    text = target.read_text(encoding="utf-8-sig")
    data = (json.loads(text) if target.suffix.lower() == ".json" else yaml.safe_load(text)) or {}
    errors = validate_resolutions(data)
    if errors:
        raise ValueError(f"invalid gap resolutions: {errors}")
    return data


def validate_resolutions(data: dict[str, Any]) -> list[str]:
    errors = []
    if not isinstance(data, dict) or not isinstance(data.get("resolutions"), list):
        return ["resolutions must be an array"]
    seen = set()
    for index, item in enumerate(data["resolutions"]):
        prefix = f"resolutions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        gap_id = str(item.get("gap_id") or "")
        if not gap_id:
            errors.append(f"{prefix}.gap_id is required")
        elif gap_id in seen:
            errors.append(f"{prefix}.gap_id is duplicated")
        seen.add(gap_id)
        kind = str(item.get("resolution_type") or "")
        if kind not in RESOLUTION_TYPES:
            errors.append(f"{prefix}.resolution_type is invalid")
        if item.get("status") not in {"pending", "approved", "rejected"}:
            errors.append(f"{prefix}.status must be pending, approved, or rejected")
        if item.get("status") == "approved" and not item.get("approved_by"):
            errors.append(f"{prefix}.approved_by is required for approval")
        if item.get("status") == "approved" and kind != "manual":
            value = item.get("value")
            if not isinstance(value, (dict, str, list)) or not value:
                errors.append(f"{prefix}.value must be a non-empty object, string, or array")
            elif kind == "binding" and isinstance(value, dict) and not any(
                    value.get(key) for key in ("target", "endpoint", "page", "table", "event", "name")):
                errors.append(f"{prefix}.binding value requires a target, endpoint, page, table, event, or name")
            elif kind == "fixture" and isinstance(value, dict) and not any(
                    value.get(key) for key in ("strategy", "recipe", "steps", "name")):
                errors.append(f"{prefix}.fixture value requires a strategy, recipe, steps, or name")
    return errors


def resolution_index(data: dict[str, Any], gap_report: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    gaps = {item["gap_id"]: item for item in gap_report.get("gaps", [])}
    index, errors = {}, []
    expected = {
        "BINDING_REVIEW_REQUIRED": "binding", "ORACLE_REVIEW_REQUIRED": "oracle",
        "FIXTURE_MISSING": "fixture", "ENVIRONMENT_MISSING": "environment",
        "BUSINESS_INPUT_REQUIRED": "business_input", "MANUAL_ONLY": "manual",
        "CAPABILITY_MISSING": "environment",
    }
    for item in data.get("resolutions", []):
        gap = gaps.get(item.get("gap_id"))
        if not gap:
            errors.append(f"unknown gap_id: {item.get('gap_id')}")
            continue
        if expected.get(gap.get("type")) != item.get("resolution_type"):
            errors.append(f"resolution type mismatch: {item.get('gap_id')}")
            continue
        index[item["gap_id"]] = item
    return index, errors


def apply_resolutions(plan: dict[str, Any], data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    index, errors = resolution_index(data, plan["gap_report"])
    if errors:
        raise ValueError(f"gap resolution mismatch: {errors}")
    approved = {gap_id: item for gap_id, item in index.items() if item.get("status") == "approved"}
    # Manual-only cases remain non-automatable even when acknowledged.
    effective_approved = {gap_id: item for gap_id, item in approved.items()
                          if next(gap for gap in plan["gap_report"]["gaps"] if gap["gap_id"] == gap_id).get("type") != "MANUAL_ONLY"}
    unresolved = [gap for gap in plan["gap_report"]["gaps"] if gap["gap_id"] not in effective_approved]
    for record in plan["readiness"]:
        record["blocking_gaps"] = [gap for gap in record["blocking_gaps"]
                                    if gap["gap_id"] not in effective_approved]
        record["status"] = "READY" if not record["blocking_gaps"] else "BLOCKED"
    for candidate in plan["binding_candidates"]:
        gap_id = f"gap:{candidate['case_id']}:{candidate['layer']}:binding_review_required"
        if gap_id in effective_approved:
            candidate["target"] = effective_approved[gap_id]["value"]
            candidate["status"] = "REVIEWED"
            candidate["confidence"] = 1.0
    for oracle in plan["oracle_plan"]:
        gap_id = f"gap:{oracle['case_id']}:{oracle['layer']}:oracle_review_required"
        if gap_id in effective_approved:
            oracle["status"] = "CONFIGURED"
            oracle["missing_inputs"] = []
            oracle["configuration"] = effective_approved[gap_id]["value"]
    for fixture in plan["fixture_requirements"]:
        matches = [item for gap_id, item in effective_approved.items()
                   if item.get("resolution_type") == "fixture" and any(
                       gap_id.startswith(f"gap:{case_id}:") for case_id in fixture["consumers"])]
        if matches:
            fixture["preferred_strategy"] = matches[0]["value"]
            fixture["missing_inputs"] = []
    counts = {kind: sum(item.get("type") == kind for item in unresolved) for kind in GAP_TYPES}
    plan["gap_report"] = {"schema_version": 1, "total": len(unresolved), "counts": counts, "gaps": unresolved}
    audit = {"schema_version": 1, "resolution_fingerprint": fingerprint(data),
             "submitted": len(data.get("resolutions", [])), "approved": len(effective_approved),
             "acknowledged_manual": len(approved) - len(effective_approved),
             "rejected": sum(item.get("status") == "rejected" for item in index.values()),
             "remaining_gaps": len(unresolved), "errors": [],
             "resolved_assets": {gap_id: item for gap_id, item in sorted(effective_approved.items())}}
    return plan, audit


def write_template(gap_report: dict[str, Any], output: str | Path,
                   existing: dict[str, Any] | None = None) -> Path:
    rows = []
    mapping = {"BINDING_REVIEW_REQUIRED": "binding", "ORACLE_REVIEW_REQUIRED": "oracle",
               "FIXTURE_MISSING": "fixture", "ENVIRONMENT_MISSING": "environment",
               "BUSINESS_INPUT_REQUIRED": "business_input", "MANUAL_ONLY": "manual",
               "CAPABILITY_MISSING": "environment"}
    previous = {item.get("gap_id"): item for item in (existing or {}).get("resolutions", [])}
    for gap in gap_report.get("gaps", []):
        old = previous.get(gap["gap_id"], {})
        resolution_type = mapping[gap["type"]]
        value_template = {"binding": {"target": ""}, "oracle": {"operator": "", "expected": None},
                          "fixture": {"strategy": "", "recipe": ""}, "environment": {"resource": ""},
                          "business_input": {"fact": ""}, "manual": {}}[resolution_type]
        rows.append({"gap_id": gap["gap_id"], "resolution_type": resolution_type,
                     "status": old.get("status", "pending"), "approved_by": old.get("approved_by", ""),
                     "value": old.get("value", value_template), "notes": old.get("notes", gap["reason"])})
    target = Path(output)
    target.write_text(yaml.safe_dump({"schema_version": 1, "resolutions": rows}, allow_unicode=True,
                                     sort_keys=False), encoding="utf-8")
    return target
