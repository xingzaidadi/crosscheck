"""
三段式批量入口(通用、零业务):对多条用例逐条跑三段,复用全局熔断器。

- 逐条调 orchestrator.run_case;
- 把每条结果映射成 FailureClass,喂给 circuit_breaker.observe:
    · spec 段打回       -> SPEC_ERROR(终态,不计入熔断,直接记打回)
    · actions 安全阻断   -> SAFETY_BLOCKED(终态,不计入熔断)
    · 其它段打回/停      -> TARGET_FAIL(可重试类,计入熔断)
    · 三段全过           -> success(清零该用例计数)
- 同一(case_id, failure_class)连续失败达阈值 -> 熔断:停批、落 BLOCKED_NEEDS_HUMAN 包;
- 熔断只停、不改判定(沿用 circuit_breaker 语义);
- 幂等可恢复:熔断计数与逐条 checkpoint 均落盘,重跑能续。

换业务不改本文件:只编排"跑一条 + 观察 + 判停",不产出业务内容。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.circuit_breaker import (
    BreakerPolicy,
    BreakerState,
    append_handoff,
    build_handoff,
    default_policy,
    observe,
)
from core.failure_class import FailureClass
from core.orchestrator import OrchestrationResult, run_case
from core.stage_contracts import STAGE_ACTIONS, STAGE_SPEC, StageVerdict
from core.stage_runner import StageAgent


@dataclass
class BatchResult:
    results: list[OrchestrationResult] = field(default_factory=list)
    stopped: bool = False
    reason: str = ""
    handoff_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stopped": self.stopped,
            "reason": self.reason,
            "handoff_path": self.handoff_path,
            "results": [result.to_dict() for result in self.results],
        }


def classify_outcome(result: OrchestrationResult) -> tuple[bool, FailureClass | None]:
    """三段式运行结果 -> (是否成功, 失败类)。成功时失败类为 None。"""
    if result.completed:
        return True, None
    stage = result.stopped_at
    outcome = next((o for o in result.outcomes if o.stage == stage), None)
    reasons = (outcome.reasons if outcome else []) or []
    if stage == STAGE_SPEC:
        return False, FailureClass.SPEC_ERROR
    if stage == STAGE_ACTIONS and any("安全阻断" in str(r) or "SAFETY" in str(r).upper()
                                      for r in reasons):
        return False, FailureClass.SAFETY_BLOCKED
    return False, FailureClass.TARGET_FAIL


def run_batch(
    agents: Mapping[str, StageAgent],
    run_dir: str | Path,
    case_ids: list[str],
    *,
    env: dict[str, Any] | None = None,
    max_retries: int = 1,
    resume: bool = True,
    policy: BreakerPolicy | None = None,
    run_id: str | None = None,
) -> BatchResult:
    """按序跑多条用例,复用熔断器;同类问题连续失败达阈值即停批并转人工。"""
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    policy = policy or default_policy()
    breaker_path = root / "breaker_state.json"
    state = _load_state(breaker_path)
    reports_dir = root / "reports"
    effective_run_id = run_id or root.name

    batch = BatchResult()
    for case_id in case_ids:
        result = run_case(agents, run_dir, case_id, env=env,
                          max_retries=max_retries, resume=resume)
        batch.results.append(result)

        success, failure_class = classify_outcome(result)
        decision = observe(state, policy, case_id=case_id,
                           failure_class=failure_class, success=success)
        _save_state(breaker_path, state)

        if decision.tripped:
            last = next((o for o in result.outcomes if o.stage == result.stopped_at), None)
            packet = build_handoff(
                decision, run_id=effective_run_id,
                triage_bucket="three_stage",
                last_verdict=(last.verdict if last else ""),
                last_details=(last.reasons if last else []),
                suggested_action=f"同类问题连续 {decision.attempts} 次未过,转人工复核")
            handoff = append_handoff(reports_dir, packet)
            batch.stopped = True
            batch.reason = decision.reason
            batch.handoff_path = str(handoff)
            break

    return batch


def _load_state(path: Path) -> BreakerState:
    if not path.exists():
        return BreakerState()
    import json
    try:
        return BreakerState.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except ValueError:
        return BreakerState()


def _save_state(path: Path, state: BreakerState) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
