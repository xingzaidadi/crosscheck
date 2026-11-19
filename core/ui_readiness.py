"""Shared readiness calculations for UI-first onboarding and CI gates."""
from __future__ import annotations

from collections import Counter
from typing import Any


def summarize_ui_readiness(report: dict[str, Any]) -> dict[str, Any]:
    rows = list(report.get("cases") or [])
    counts = Counter(str(row.get("status") or "UNKNOWN") for row in rows)
    total = len(rows)
    executable = counts.get("UI_EXECUTABLE", 0)
    return {
        "total": total,
        "counts": dict(counts),
        "executable_rate": round(executable / total, 4) if total else 0.0,
        "blocking_rate": round((counts.get("UI_BLOCKED", 0) + counts.get("UI_BINDING_REQUIRED", 0)) / total, 4)
        if total else 0.0,
        "ready": bool(total and executable == total),
    }


def gap_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in report.get("cases") or [] if row.get("status") != "UI_EXECUTABLE"]
