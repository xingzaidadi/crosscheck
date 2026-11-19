"""Diagnose common UI/API/DB reconciliation mismatches."""
from __future__ import annotations

from typing import Any


def diagnose_count_mismatch(api_count: int, db_count: int, context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    hypotheses = []
    if not context.get("tenant_filter_verified"):
        hypotheses.append("tenant_scope")
    if not context.get("permission_scope_verified"):
        hypotheses.append("permission_scope")
    if not context.get("soft_delete_filter_verified"):
        hypotheses.append("soft_delete")
    if not context.get("status_filter_verified"):
        hypotheses.append("status_mapping")
    return {"matched": api_count == db_count, "api_count": api_count, "db_count": db_count,
            "delta": api_count - db_count, "hypotheses": hypotheses,
            "verdict": "PASS" if api_count == db_count else "INCONCLUSIVE"}


def compare_fields(
    ui: dict[str, Any], api: dict[str, Any], *, transforms: dict[str, dict[Any, Any]] | None = None,
) -> dict[str, Any]:
    transforms = transforms or {}
    mismatches = []
    for field, ui_value in ui.items():
        api_value = api.get(field)
        mapping = transforms.get(field) or {}
        normalized_api = mapping.get(api_value, api_value)
        if str(ui_value).strip() != str(normalized_api).strip():
            mismatches.append({"field": field, "ui": ui_value, "api": api_value,
                               "normalized_api": normalized_api})
    return {"matched": not mismatches, "mismatches": mismatches,
            "verdict": "PASS" if not mismatches else "FAIL"}
