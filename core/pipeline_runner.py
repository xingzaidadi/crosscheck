"""Deterministic pilot/batch runner with checkpoints and circuit breaking."""
from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.interfaces import CaseResult, Verdict
from core.suite_compiler import plan_hash
from core.circuit_breaker import (
    BreakerPolicy,
    BreakerState,
    append_handoff,
    build_handoff,
    observe,
)
from core.failure_class import classify_verdict


@dataclass
class PipelineOutcome:
    results: list[CaseResult]
    stopped: bool = False
    reason: str = ""


def run_pipeline(
    specs: list,
    execute: Callable,
    run_dir: str | Path,
    *,
    pilot_size: int = 3,
    resume: bool = True,
    env_error_limit: int = 3,
    registry=None,
    run_id: str | None = None,
    environment: str = "unknown",
    breaker_policy: BreakerPolicy | None = None,
) -> PipelineOutcome:
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = root / "checkpoint.json"
    breaker_path = root / "breaker_state.json"
    breaker_state = _load_breaker_state(breaker_path) if breaker_policy is not None else None
    identity_path = root / "plan_identity.json"
    identity = plan_hash(specs) if all(hasattr(spec, "raw") and hasattr(spec, "__dataclass_fields__") for spec in specs) else str([
        (spec.case_id, spec.mode) for spec in specs])
    registry_run_id = run_id or root.name
    if registry is not None and registry.run(registry_run_id) is None:
        registry.create_run(registry_run_id, identity, environment)
    if resume and checkpoint.exists():
        if not identity_path.exists():
            raise RuntimeError("checkpoint has no plan identity; refusing unsafe resume")
        previous = json.loads(identity_path.read_text(encoding="utf-8"))
        if previous.get("plan_hash") != identity:
            raise RuntimeError("execution plan changed; refusing checkpoint reuse")
    identity_path.write_text(json.dumps({"plan_hash": identity}), encoding="utf-8")
    completed = _load_checkpoint(checkpoint) if resume else {}
    results: list[CaseResult] = [_result_from_dict(item["result"]) for item in completed.values()
                                 if isinstance(item, dict) and item.get("result")]
    ordered = _pilot_order(specs, pilot_size)
    consecutive_env = 0
    pilot_passed = False

    for index, spec in enumerate(ordered):
        if spec.case_id in completed:
            if completed[spec.case_id].get("verdict") == Verdict.PASS.value:
                pilot_passed = True
            elif breaker_policy is not None and breaker_state is not None:
                # A previously-completed non-PASS case is being resumed. It is skipped
                # below, but the breaker must still count it — otherwise resume=True
                # (the default) makes the breaker a no-op for a persistently failing case.
                prior = _result_from_dict(completed[spec.case_id]["result"])
                tripped = _observe_and_maybe_handoff(
                    breaker_state, breaker_policy, breaker_path, root,
                    spec=spec, result=prior, registry=registry, registry_run_id=registry_run_id,
                )
                if tripped is not None:
                    return PipelineOutcome(results, True, tripped)
            continue
        try:
            result = execute(spec)
        except Exception as exc:  # unknown remote state must not be treated as a normal failure
            result = CaseResult(case_id=spec.case_id, verdict=Verdict.ENV_ERROR,
                                details=[f"执行异常，远端状态未知: {exc}"], cleanup_ok=False)
            if registry is not None:
                registry.save_step(registry_run_id, spec.case_id,
                                   str((getattr(spec, "raw", {}) or {}).get("action_ref") or spec.mode),
                                   "unknown", "; ".join(result.details))
        else:
            if registry is not None:
                registry.save_step(registry_run_id, spec.case_id,
                                   str((getattr(spec, "raw", {}) or {}).get("action_ref") or spec.mode),
                                   "succeeded" if result.verdict is Verdict.PASS else "failed",
                                   "; ".join(result.details))
        read_only = spec.mode == "reconcile" and not getattr(spec, "data_prep", None)
        if result.verdict is Verdict.ENV_ERROR and read_only and result.cleanup_ok:
            result = execute(spec)
        results.append(result)
        if result.verdict is Verdict.PASS:
            pilot_passed = True
        completed[spec.case_id] = {"verdict": result.verdict.value, "cleanup_ok": result.cleanup_ok,
                                   "result": _result_to_dict(result)}
        _save_checkpoint(checkpoint, completed)

        if breaker_policy is not None and breaker_state is not None:
            tripped = _observe_and_maybe_handoff(
                breaker_state, breaker_policy, breaker_path, root,
                spec=spec, result=result, registry=registry, registry_run_id=registry_run_id,
            )
            if tripped is not None:
                return PipelineOutcome(results, True, tripped)

        if not result.cleanup_ok:
            if registry is not None:
                registry.set_run_status(registry_run_id, "failed")
            return PipelineOutcome(results, True, f"cleanup failed: {spec.case_id}")
        if result.verdict is Verdict.ENV_ERROR:
            consecutive_env += 1
            if consecutive_env >= env_error_limit:
                if registry is not None:
                    registry.set_run_status(registry_run_id, "stopped")
                return PipelineOutcome(results, True, f"environment circuit breaker: {consecutive_env}")
        else:
            consecutive_env = 0
        if result.verdict in {Verdict.ABORTED, Verdict.INVALID_SPEC}:
            if registry is not None:
                registry.set_run_status(registry_run_id, "stopped")
            return PipelineOutcome(results, True, f"safety stop: {spec.case_id}/{result.verdict.value}")

        if index < min(pilot_size, len(ordered)) and result.verdict not in {Verdict.PASS, Verdict.FAIL}:
            if registry is not None:
                registry.set_run_status(registry_run_id, "stopped")
            return PipelineOutcome(results, True, f"pilot not conclusive: {spec.case_id}/{result.verdict.value}")
        if pilot_size > 0 and index + 1 == min(pilot_size, len(ordered)) and not pilot_passed:
            if registry is not None:
                registry.set_run_status(registry_run_id, "stopped")
            return PipelineOutcome(results, True, "pilot has no passing case")

    if registry is not None:
        registry.set_run_status(registry_run_id, "completed")
    return PipelineOutcome(results)


def _observe_and_maybe_handoff(
    state: BreakerState,
    policy: BreakerPolicy,
    breaker_path: Path,
    root: Path,
    *,
    spec,
    result: CaseResult,
    registry,
    registry_run_id: str,
) -> str | None:
    """Record one case outcome in the breaker; on trip, write handoff and return a stop reason.

    Returns ``None`` when the run should continue, or the stop reason string when it trips.
    """
    failure_class = _failure_class_for(result)
    decision = observe(
        state, policy,
        case_id=spec.case_id, failure_class=failure_class,
        success=result.verdict is Verdict.PASS,
    )
    _save_breaker_state(breaker_path, state)
    if not decision.tripped:
        return None
    packet = build_handoff(
        decision,
        run_id=registry_run_id,
        last_verdict=result.verdict.value,
        last_details=[detail[:500] for detail in result.details],  # bounded; file is internal-sensitive
        evidence_refs=[str((root / "events.jsonl"))],
        suggested_action="human_review_repeated_failure",
    )
    append_handoff(root, packet)
    if registry is not None:
        registry.set_run_status(registry_run_id, "stopped")
    return f"BLOCKED_NEEDS_HUMAN: {spec.case_id}/{decision.failure_class}"


def _failure_class_for(result: CaseResult):
    # Cleanup failures must stay a CLEANUP_FAILED signal even if an upstream
    # failure_class field says otherwise — a dirty environment is more urgent
    # than a repeated-failure trip and is handled by the cleanup stop path.
    if not result.cleanup_ok:
        from core.failure_class import FailureClass
        return FailureClass.CLEANUP_FAILED
    if result.failure_class:
        try:
            from core.failure_class import FailureClass
            return FailureClass(result.failure_class)
        except ValueError:
            pass
    return classify_verdict(result.verdict.value, cleanup_ok=result.cleanup_ok)


def _load_breaker_state(path: Path) -> BreakerState:
    if not path.exists():
        return BreakerState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"breaker state corrupted: {path}") from exc
    return BreakerState.from_dict(data)


def _save_breaker_state(path: Path, state: BreakerState) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _pilot_order(specs: list, pilot_size: int) -> list:
    risk = {"ui": 0, "api": 1, "write": 1, "reconcile": 2, "script": 3, "manual": 4}
    pilots = sorted(specs, key=lambda spec: (risk.get(spec.mode, 5), spec.case_id))[:pilot_size]
    ids = {spec.case_id for spec in pilots}
    return pilots + [spec for spec in specs if spec.case_id not in ids]


def _load_checkpoint(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"checkpoint corrupted: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"checkpoint invalid: {path}")
    return data


def _save_checkpoint(path: Path, data: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _result_to_dict(result: CaseResult) -> dict:
    data = asdict(result)
    data["verdict"] = result.verdict.value
    return data


def _result_from_dict(data: dict) -> CaseResult:
    values = dict(data)
    values["verdict"] = Verdict(values["verdict"])
    valid = set(CaseResult.__dataclass_fields__)
    return CaseResult(**{key: value for key, value in values.items() if key in valid})
