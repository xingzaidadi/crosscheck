"""Deterministic pilot/batch runner with checkpoints and circuit breaking."""
from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.interfaces import CaseResult, Verdict
from core.suite_compiler import plan_hash


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
) -> PipelineOutcome:
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = root / "checkpoint.json"
    identity_path = root / "plan_identity.json"
    identity = plan_hash(specs) if all(hasattr(spec, "raw") for spec in specs) else str([
        (spec.case_id, spec.mode) for spec in specs])
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
            continue
        result = execute(spec)
        read_only = spec.mode == "reconcile" and not getattr(spec, "data_prep", None)
        if result.verdict is Verdict.ENV_ERROR and read_only and result.cleanup_ok:
            result = execute(spec)
        results.append(result)
        if result.verdict is Verdict.PASS:
            pilot_passed = True
        completed[spec.case_id] = {"verdict": result.verdict.value, "cleanup_ok": result.cleanup_ok,
                                   "result": _result_to_dict(result)}
        _save_checkpoint(checkpoint, completed)

        if not result.cleanup_ok:
            return PipelineOutcome(results, True, f"cleanup failed: {spec.case_id}")
        if result.verdict is Verdict.ENV_ERROR:
            consecutive_env += 1
            if consecutive_env >= env_error_limit:
                return PipelineOutcome(results, True, f"environment circuit breaker: {consecutive_env}")
        else:
            consecutive_env = 0
        if result.verdict in {Verdict.ABORTED, Verdict.INVALID_SPEC}:
            return PipelineOutcome(results, True, f"safety stop: {spec.case_id}/{result.verdict.value}")

        if index < min(pilot_size, len(ordered)) and result.verdict not in {Verdict.PASS, Verdict.FAIL}:
            return PipelineOutcome(results, True, f"pilot not conclusive: {spec.case_id}/{result.verdict.value}")
        if pilot_size > 0 and index + 1 == min(pilot_size, len(ordered)) and not pilot_passed:
            return PipelineOutcome(results, True, "pilot has no passing case")

    return PipelineOutcome(results)


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
