"""Independent execution plans for UI, API and DB verification layers.

The aggregate in :mod:`core.layered_execution` is intentionally kept as a
reporting primitive.  This module adds the execution boundary that was
previously missing: each layer owns its checkpoint, retry policy and result,
and the cross-layer verdict is derived only after all selected subplans have
finished.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from core.layered_execution import LayerResult, LayerVerdict, aggregate


LayerRunner = Callable[[dict[str, Any]], LayerResult | dict[str, Any] | bool]


@dataclass(frozen=True)
class LayerSubplan:
    """Executable contract for one verification layer."""

    layer: str
    required: bool = True
    max_attempts: int = 1
    checkpoint: str = ""
    retry_on: frozenset[LayerVerdict] = frozenset(
        {LayerVerdict.ENV_ERROR, LayerVerdict.INCONCLUSIVE}
    )

    def __post_init__(self) -> None:
        if not self.layer.strip():
            raise ValueError("layer is required")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")


@dataclass
class SubplanExecution:
    layer: str
    attempts: int = 0
    checkpoint: str = ""
    recovered: bool = False
    result: LayerResult | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        result = self.result
        return {
            "layer": self.layer,
            "attempts": self.attempts,
            "checkpoint": self.checkpoint,
            "recovered": self.recovered,
            "verdict": result.verdict.value if result else LayerVerdict.NOT_RUN.value,
            "evidence": list(result.evidence) if result else [],
            "details": list(result.details) if result else [],
            "history": list(self.history),
        }


def _coerce_result(layer: str, value: LayerResult | dict[str, Any] | bool) -> LayerResult:
    if isinstance(value, LayerResult):
        if value.layer != layer:
            raise ValueError(f"runner returned layer {value.layer!r}, expected {layer!r}")
        return value
    if isinstance(value, bool):
        return LayerResult(layer, LayerVerdict.PASS if value else LayerVerdict.FAIL)
    if isinstance(value, dict):
        verdict = value.get("verdict", LayerVerdict.INCONCLUSIVE)
        try:
            verdict = LayerVerdict(verdict)
        except ValueError as exc:
            raise ValueError(f"unsupported layer verdict: {verdict!r}") from exc
        return LayerResult(
            layer=layer,
            verdict=verdict,
            evidence=list(value.get("evidence") or []),
            details=list(value.get("details") or []),
            checkpoint=str(value.get("checkpoint") or ""),
        )
    raise TypeError(f"unsupported runner result: {type(value).__name__}")


def execute_subplan(
    subplan: LayerSubplan,
    runner: LayerRunner,
    *,
    context: dict[str, Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    retry_delay_s: float = 0,
) -> SubplanExecution:
    """Run one layer with bounded retry and checkpoint preservation."""
    execution = SubplanExecution(layer=subplan.layer, checkpoint=subplan.checkpoint)
    payload = dict(context or {})
    payload.update({"layer": subplan.layer, "checkpoint": subplan.checkpoint})
    for attempt in range(1, subplan.max_attempts + 1):
        execution.attempts = attempt
        try:
            result = _coerce_result(subplan.layer, runner(payload))
        except Exception as exc:  # runner errors are environment failures
            result = LayerResult(
                subplan.layer,
                LayerVerdict.ENV_ERROR,
                details=[f"runner error: {exc}"],
                checkpoint=subplan.checkpoint,
            )
        execution.result = result
        execution.checkpoint = result.checkpoint or subplan.checkpoint
        execution.history.append({"attempt": attempt, "verdict": result.verdict.value})
        if result.verdict not in subplan.retry_on or attempt >= subplan.max_attempts:
            break
        execution.recovered = True
        if retry_delay_s > 0:
            sleep(retry_delay_s)
    return execution


def execute_subplans(
    subplans: Iterable[LayerSubplan],
    runners: dict[str, LayerRunner],
    *,
    context: dict[str, Any] | None = None,
    retry_delay_s: float = 0,
) -> dict[str, Any]:
    """Execute independent subplans and derive a cross-layer verdict."""
    plans = list(subplans)
    executions: list[SubplanExecution] = []
    for subplan in plans:
        runner = runners.get(subplan.layer)
        if runner is None:
            execution = SubplanExecution(layer=subplan.layer, checkpoint=subplan.checkpoint)
            execution.result = LayerResult(
                subplan.layer,
                LayerVerdict.NOT_RUN,
                details=["runner is not registered"],
                checkpoint=subplan.checkpoint,
            )
            executions.append(execution)
            continue
        executions.append(
            execute_subplan(
                subplan,
                runner,
                context=context,
                retry_delay_s=retry_delay_s,
            )
        )
    results = [
        item.result
        for item in executions
        if item.result is not None and not any(
            detail == "runner is not registered" for detail in item.result.details
        )
    ]
    required = {item.layer for item in plans if item.required}
    optional = {item.layer for item in plans if not item.required}
    report = aggregate(results, {"required": required, "optional": optional})
    verdict = report["verdict"]
    required_results = [result for result in results if result.layer in required]
    if any(result.verdict == LayerVerdict.FAIL for result in required_results):
        verdict = "CROSS_FAIL"
    elif verdict == LayerVerdict.PASS.value and len(results) > 1:
        verdict = "CROSS_PASS"
    elif verdict == LayerVerdict.INCONCLUSIVE.value and len(executions) > 1:
        verdict = "CROSS_INCONCLUSIVE"
    report["verdict"] = verdict
    report["subplans"] = [item.as_dict() for item in executions]
    return report
