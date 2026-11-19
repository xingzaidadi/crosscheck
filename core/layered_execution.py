"""Independent UI/API/DB subplan result aggregation."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LayerVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    ENV_ERROR = "ENV_ERROR"
    PREREQUISITE_FAILED = "PREREQUISITE_FAILED"
    NOT_RUN = "NOT_RUN"


@dataclass
class LayerResult:
    layer: str
    verdict: LayerVerdict
    evidence: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    checkpoint: str = ""


def aggregate(results: list[LayerResult], required: set[str] | dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(required, dict):
        required_layers = set(required.get("required") or [])
        optional_layers = set(required.get("optional") or [])
        deferred_layers = set(required.get("deferred") or [])
    else:
        required_layers = set(required or {result.layer for result in results})
        optional_layers = set()
        deferred_layers = set()
    by_layer = {result.layer: result for result in results}
    missing = sorted(required_layers - set(by_layer))
    if missing:
        verdict = LayerVerdict.INCONCLUSIVE
    else:
        selected = [by_layer[layer].verdict for layer in required_layers]
        if any(value == LayerVerdict.FAIL for value in selected):
            verdict = LayerVerdict.FAIL
        elif any(value in {LayerVerdict.ENV_ERROR, LayerVerdict.PREREQUISITE_FAILED, LayerVerdict.INCONCLUSIVE, LayerVerdict.NOT_RUN} for value in selected):
            verdict = LayerVerdict.INCONCLUSIVE
        else:
            verdict = LayerVerdict.PASS
    optional_failures = sorted(layer for layer in optional_layers
                               if layer in by_layer and by_layer[layer].verdict == LayerVerdict.FAIL)
    return {
        "verdict": verdict.value,
        "layers": {name: {
            "verdict": result.verdict.value,
            "evidence": list(result.evidence),
            "details": list(result.details),
            "checkpoint": result.checkpoint,
        } for name, result in by_layer.items()},
        "missing_required": missing,
        "optional_failures": optional_failures,
        "deferred": sorted(deferred_layers),
    }
