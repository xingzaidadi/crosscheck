"""Local Case v2 runner for deterministic business-arsenal acceptance."""
from __future__ import annotations

from typing import Any

from .case_v2 import validate_v2
from .layered_execution import LayerResult, LayerVerdict, aggregate
from .oracle import evaluate


def run_case(case: dict[str, Any], capability_pack, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    errors = validate_v2(case)
    if errors:
        return {"case_id": case.get("case_id", ""), "verdict": "INVALID_SPEC", "errors": errors}
    context = dict(context or {})
    action = dict(case["action"])
    capability = str(action["capability"])
    try:
        result = capability_pack.execute(capability, inputs=dict(action.get("inputs") or {}), context=context)
        context.update(result.get("outputs") or {})
    except Exception as exc:
        return {"case_id": case["case_id"], "verdict": "PREREQUISITE_FAILED",
                "errors": [str(exc)], "layers": {}}
    evidence = dict(result.get("evidence") or {})
    oracle_result = evaluate(list(case.get("oracles") or []), evidence)
    layers = []
    for proof in sorted({str(item.get("proof")) for item in case.get("oracles") or []}):
        layer_oracles = [item for item in case["oracles"] if item.get("proof") == proof]
        layer_outcome = evaluate(layer_oracles, evidence)
        layers.append(LayerResult(proof, LayerVerdict.PASS if layer_outcome["passed"] else LayerVerdict.FAIL,
                                  evidence=[proof], details=layer_outcome["failed"]))
    layer_policy = case.get("layers") or {"required": [item.layer for item in layers]}
    aggregate_result = aggregate(layers, layer_policy if isinstance(layer_policy, dict) else set(layer_policy))
    return {"case_id": case["case_id"], "verdict": "PASS" if oracle_result["passed"] else "FAIL",
            "context": context, "evidence": evidence, "oracle_results": oracle_result,
            "layer_aggregate": aggregate_result, "layers": [item.__dict__ for item in layers]}
