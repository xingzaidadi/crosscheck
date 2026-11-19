"""UI-first readiness and verdict semantics.

UI execution is independently valuable. API and DB coverage enrich diagnosis
but do not block a UI case unless the case explicitly declares those layers as
required for its current phase.
"""
from __future__ import annotations

from typing import Any


def phase_layers(case: dict[str, Any], phase: str = "ui") -> dict[str, list[str]]:
    configured = case.get("layers") or {}
    if phase == "ui":
        required = ["ui"]
        optional = sorted(set(configured.get("required") or []) - {"ui"})
        deferred = sorted(set(configured.get("deferred") or []))
    else:
        required = list(configured.get("required") or [])
        optional = list(configured.get("optional") or [])
        deferred = list(configured.get("deferred") or [])
    return {"required": required, "optional": optional, "deferred": deferred}


def ui_readiness(case: dict[str, Any], provided_layers: list[str], *, approved: bool,
                 blocked: str = "") -> dict[str, Any]:
    provided = set(provided_layers)
    reasons = []
    if blocked:
        reasons.append(blocked)
    if not approved:
        reasons.append("case is not human_verified")
    if "ui" not in provided:
        reasons.append("UI binding is missing")
    optional = sorted(provided & {"api", "db"})
    return {"executable": not reasons, "required_layers": ["ui"],
            "optional_covered": optional, "reasons": reasons}


def ui_verdict(ui_passed: bool, *, api: str = "NOT_COVERED", db: str = "NOT_COVERED") -> dict[str, Any]:
    verdict = "UI_PASS" if ui_passed else "UI_FAIL"
    return {"verdict": verdict, "ui": "PASS" if ui_passed else "FAIL", "api": api, "db": db,
            "cross_verdict": "NOT_EVALUATED"}
