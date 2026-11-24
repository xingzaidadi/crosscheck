"""
三段式流水线编排器(DSH 总控,通用、零业务)。

职责:
  - 读 stage_checkpoint.json:哪些段已过闸(过闸的段只读、不重跑);
  - 按 spec -> actions -> evidence 顺序,逐段派对应子 Agent;
  - 每段跑完走 run_stage(写作用域门禁 + 契约校验):
      · PASS -> 落产物 artifacts/<stage>.json + 记 checkpoint,进下一段;
      · REJECT -> 在本段 bounded 重试(默认 1 次);仍不过 -> 打回,停在本段;
  - 上游产物对下游只读传入;某段打回只重跑该段,不触碰上游产物;
  - plan_identity.json 锁定:上游产物变了(哈希变)拒绝复用下游旧 checkpoint。

不改判定规则本身(校验契约在 stage_contracts,从代码基线读)。
编排器只负责"派段 + 判过闸 + 落盘 + 复用",不产出业务内容。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.stage_contracts import STAGE_ARTIFACT, STAGES, StageVerdict
from core.stage_runner import StageAgent, StageContext, StageRun, run_stage


@dataclass
class StageOutcome:
    stage: str
    verdict: str
    reasons: list[str] = field(default_factory=list)
    attempts: int = 0
    artifact_hash: str = ""
    reused: bool = False


@dataclass
class OrchestrationResult:
    case_id: str
    completed: bool
    stopped_at: str = ""
    outcomes: list[StageOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "completed": self.completed,
            "stopped_at": self.stopped_at,
            "outcomes": [vars(outcome) for outcome in self.outcomes],
        }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


class Orchestrator:
    """逐用例跑三段式;per-stage checkpoint,支持安全续跑与精确打回重跑。"""

    def __init__(
        self,
        agents: Mapping[str, StageAgent],
        run_dir: str | Path,
        *,
        case_id: str,
        env: dict[str, Any] | None = None,
        max_retries: int = 1,
        resume: bool = True,
    ) -> None:
        missing = [stage for stage in STAGES if stage not in agents]
        if missing:
            raise ValueError(f"缺少子 Agent: {missing}")
        self.agents = dict(agents)
        self.case_id = case_id
        self.env = dict(env or {})
        self.max_retries = max(0, int(max_retries))
        self.resume = resume
        self.root = Path(run_dir) / case_id
        self.art_dir = self.root / "artifacts"
        self.checkpoint_path = self.root / "stage_checkpoint.json"
        self.identity_path = self.root / "plan_identity.json"

    # ── 产物 I/O ──
    def _artifact_path(self, stage: str) -> Path:
        return self.art_dir / f"{stage}.json"

    def _load_artifact(self, stage: str) -> dict[str, Any]:
        return _read_json(self._artifact_path(stage))

    def _save_artifact(self, stage: str, artifact: dict[str, Any]) -> None:
        _write_json(self._artifact_path(stage), artifact)

    # ── checkpoint ──
    def _load_checkpoint(self) -> dict[str, Any]:
        return _read_json(self.checkpoint_path) if self.resume else {}

    def _save_checkpoint(self, data: dict[str, Any]) -> None:
        _write_json(self.checkpoint_path, data)

    def _upstream(self, stage: str) -> dict[str, Any]:
        """汇集本段之前所有已过闸段的产物(只读传入)。"""
        upstream: dict[str, Any] = {}
        for prior in STAGES:
            if prior == stage:
                break
            upstream.update(self._load_artifact(prior))
        return upstream

    def _passed_hashes(self, checkpoint: dict[str, Any]) -> dict[str, str]:
        return {stage: info.get("artifact_hash", "")
                for stage, info in checkpoint.items()
                if isinstance(info, dict) and info.get("verdict") == StageVerdict.PASS.value}

    def run(self) -> OrchestrationResult:
        self.root.mkdir(parents=True, exist_ok=True)
        checkpoint = self._load_checkpoint()
        # 续跑安全:记录上游产物指纹,若上游产物内容变了,拒绝复用下游旧 checkpoint。
        identity = _read_json(self.identity_path) if self.resume else {}

        outcomes: list[StageOutcome] = []
        for stage in STAGES:
            prior_passed = (
                isinstance(checkpoint.get(stage), dict)
                and checkpoint[stage].get("verdict") == StageVerdict.PASS.value
                and self._artifact_path(stage).exists()
            )
            if prior_passed:
                outcomes.append(StageOutcome(
                    stage=stage, verdict=StageVerdict.PASS.value,
                    artifact_hash=checkpoint[stage].get("artifact_hash", ""),
                    attempts=checkpoint[stage].get("attempts", 0), reused=True,
                ))
                continue

            # 上游指纹校验:若此前记过上游指纹且现在对不上,说明上游产物变了。
            upstream = self._upstream(stage)
            upstream_fp = _fingerprint(upstream)
            prev_fp = identity.get(stage)
            if prev_fp is not None and prev_fp != upstream_fp:
                # 上游变 -> 本段及其下游旧结论作废(不复用),从本段重新跑。
                checkpoint.pop(stage, None)

            run = self._run_with_retry(stage, upstream)
            identity[stage] = upstream_fp
            self._save_artifact(stage, run.artifact)
            info = {
                "verdict": run.check.verdict.value,
                "reasons": run.check.reasons,
                "artifact_hash": run.check.artifact_hash,
                "attempts": run.attempts,
            }
            checkpoint[stage] = info
            self._save_checkpoint(checkpoint)
            _write_json(self.identity_path, identity)

            outcomes.append(StageOutcome(
                stage=stage, verdict=run.check.verdict.value, reasons=run.check.reasons,
                attempts=run.attempts, artifact_hash=run.check.artifact_hash,
            ))

            if not run.ok:
                return OrchestrationResult(self.case_id, False, stopped_at=stage, outcomes=outcomes)

        return OrchestrationResult(self.case_id, True, outcomes=outcomes)

    def _run_with_retry(self, stage: str, upstream: dict[str, Any]) -> "_AttemptedRun":
        agent = self.agents[stage]
        attempts = 0
        last: StageRun | None = None
        while attempts <= self.max_retries:
            attempts += 1
            context = StageContext(stage=stage, case_id=self.case_id,
                                   upstream=dict(upstream), env=dict(self.env))
            last = run_stage(agent, context)
            if last.ok:
                break
        attempted = _AttemptedRun(stage=last.stage, artifact=last.artifact,
                                  check=last.check, scope_violation=last.scope_violation)
        attempted.attempts = attempts
        return attempted


@dataclass
class _AttemptedRun(StageRun):
    attempts: int = 0


def _fingerprint(upstream: dict[str, Any]) -> str:
    from core.stage_contracts import artifact_hash
    return artifact_hash(upstream)


def run_case(
    agents: Mapping[str, StageAgent],
    run_dir: str | Path,
    case_id: str,
    *,
    env: dict[str, Any] | None = None,
    max_retries: int = 1,
    resume: bool = True,
) -> OrchestrationResult:
    """便捷入口:跑单条用例的三段式。"""
    return Orchestrator(agents, run_dir, case_id=case_id, env=env,
                        max_retries=max_retries, resume=resume).run()
