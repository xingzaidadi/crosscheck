"""Unified G0/G1/G2/G-A/G-L gate evaluator."""
from __future__ import annotations

from typing import Any

from .case_auditor import audit_cases
from .manifest import verify_manifest


def evaluate_gates(*, cases: list[dict[str, Any]], manifest: dict[str, Any] | None = None,
                   capabilities: list[Any] | None = None, assets: list[dict[str, Any]] | None = None,
                   layer_results: list[dict[str, Any]] | None = None,
                   facts: dict[str, Any] | None = None) -> dict[str, Any]:
    case_report = audit_cases(cases)
    gates = {
        "G0": not bool((facts or {}).get("missing")),
        "G1": case_report["ready"] == case_report["total"],
        "G2": bool(manifest and not verify_manifest(manifest)),
        "G-A": all(item.get("state") == "healthy" and item.get("evidence") for item in (assets or [])),
        "G-L": all(item.get("verdict") not in {"NOT_RUN", "INCONCLUSIVE"} for item in (layer_results or [])),
    }
    return {"passed": all(gates.values()), "gates": gates, "case_audit": case_report,
            "manifest_errors": verify_manifest(manifest) if manifest else ["manifest missing"]}
