"""
子 Agent 协议 + 写作用域隔离门禁(通用、零业务、可测)。

三段式里每段由一个"子 Agent"负责。本文件给出:
  - StageAgent 协议:子 Agent 只需实现 produce(stage, context) -> dict 产物;
  - write_scope(stage):每段允许写的产物键白名单(派生自 stage_contracts);
  - enforce_write_scope():门禁——子 Agent 产物只能落在本段白名单键内,
    越界(试图写上游/下游产物)即拒绝,从机制上杜绝"改一处、全流程重写";
  - run_stage():跑一段 = 子 Agent 产出 -> 写作用域门禁 -> 契约校验,
    返回 StageRun(产物 + CheckResult),判定通过/打回。

本文件不读写磁盘、不碰 LLM,纯编排与门禁。落盘/调度在 orchestrator。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from core.stage_contracts import (
    STAGE_ARTIFACT,
    STAGES,
    CheckResult,
    StageVerdict,
    validate,
)


class StageAgent(Protocol):
    """子 Agent 协议:给定段名与只读上下文,产出该段制品(dict)。

    产物约定:{<artifact_key>: {...}},artifact_key 由 STAGE_ARTIFACT[stage] 决定。
    子 Agent 不得写入其他段的键(由 enforce_write_scope 强制)。
    """

    def produce(self, stage: str, context: "StageContext") -> dict[str, Any]:
        ...


@dataclass
class StageContext:
    """传给子 Agent 的只读上下文:上游产物 + 环境信息。

    upstream 是前序各段的产物(只读);子 Agent 可读不可改。
    """
    stage: str
    case_id: str
    upstream: dict[str, Any] = field(default_factory=dict)
    env: dict[str, Any] = field(default_factory=dict)

    def upstream_artifact(self, stage: str) -> dict[str, Any]:
        """取某上游段的产物键内容(只读副本语义由调用方保证)。"""
        key = STAGE_ARTIFACT.get(stage, stage)
        return (self.upstream.get(key) or {})


@dataclass
class StageRun:
    """一段的运行结果:产物 + 契约校验结论。"""
    stage: str
    artifact: dict[str, Any]
    check: CheckResult
    scope_violation: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.scope_violation and self.check.ok


class WriteScopeError(Exception):
    """子 Agent 产物越界写入(写了非本段的产物键)。"""


def write_scope(stage: str) -> set[str]:
    """本段允许写入的产物键白名单。"""
    key = STAGE_ARTIFACT.get(stage)
    return {key} if key else set()


def enforce_write_scope(stage: str, artifact: dict[str, Any]) -> list[str]:
    """
    门禁:产物的顶层键必须全部落在本段白名单内。

    返回越界键列表(空=合规)。orchestrator 据此判定是否拒收产物。
    """
    if not isinstance(artifact, dict):
        return ["产物不是对象"]
    allowed = write_scope(stage)
    violations = [key for key in artifact if key not in allowed]
    return [f"越界写入产物键: {key}(本段仅允许 {sorted(allowed)})" for key in violations]


def run_stage(agent: StageAgent, context: StageContext) -> StageRun:
    """
    跑一段:子 Agent 产出 -> 写作用域门禁 -> 契约校验。

    - 写作用域越界:直接 REJECT,不进契约校验(产物不可信)。
    - 契约不过:REJECT,reasons 给出精确打回原因(只重跑本段)。
    """
    stage = context.stage
    if stage not in STAGES:
        raise ValueError(f"未知阶段: {stage}")

    artifact = agent.produce(stage, context)

    violations = enforce_write_scope(stage, artifact)
    if violations:
        check = CheckResult(stage, StageVerdict.REJECT, list(violations))
        return StageRun(stage, artifact if isinstance(artifact, dict) else {}, check, violations)

    check = validate(stage, artifact)
    return StageRun(stage, artifact, check)
