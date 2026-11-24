"""
阶段产物契约(通用、零业务、纯函数、可测)。

三段式流水线每段产出一个"制品"(artifact),每段配一个"校验门禁"(checkpoint):
    CP-1 用例转操作  -> exec_spec 制品  -> validate_spec()
    CP-2 UI 操作     -> actions  制品  -> validate_actions()
    CP-3 操作后验证  -> evidence 制品  -> validate_evidence()

设计原则:
  - 契约只做"结构/完整性/可解析"的确定性校验,不碰 LLM、不认任何业务词。
  - 校验结果用 StageVerdict 表达:PASS(过闸,进下一段)/ REJECT(打回,只重跑本段)。
  - 产物自带 schema 版本与内容哈希,便于 orchestrator 判定"产物是否改变"。
  - 纯函数:输入 dict,输出 CheckResult;不读磁盘、不写磁盘(落盘在 orchestrator)。

换业务不改本文件:业务事实落 workspace,本文件只认通用结构。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


SCHEMA_VERSION = "1"

# 三段固定顺序与制品名。orchestrator 据此派段、串接。
STAGE_SPEC = "spec"        # 用例转操作
STAGE_ACTIONS = "actions"  # UI 操作
STAGE_EVIDENCE = "evidence"  # 操作后验证
STAGES: tuple[str, ...] = (STAGE_SPEC, STAGE_ACTIONS, STAGE_EVIDENCE)

# 每段只写自己的产物键(写作用域隔离的"白名单"根据此派生)。
STAGE_ARTIFACT = {
    STAGE_SPEC: "exec_spec",
    STAGE_ACTIONS: "actions",
    STAGE_EVIDENCE: "evidence",
}


class StageVerdict(str, Enum):
    PASS = "pass"        # 产物过闸,允许进入下一段
    REJECT = "reject"    # 产物不合契约,打回本段(只重跑本段,上游只读不动)


@dataclass
class CheckResult:
    """单段校验结论。reasons 给"缺了什么/差在哪",供打回时精确修。"""
    stage: str
    verdict: StageVerdict
    reasons: list[str] = field(default_factory=list)
    artifact_hash: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict == StageVerdict.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "verdict": self.verdict.value,
            "reasons": list(self.reasons),
            "artifact_hash": self.artifact_hash,
        }


def artifact_hash(artifact: Any) -> str:
    """产物内容哈希(排序键、稳定):判定产物是否变化、作为 checkpoint 指纹。"""
    payload = json.dumps(artifact, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require(container: Any, key: str, reasons: list[str], *, non_empty: bool = False) -> bool:
    if not isinstance(container, dict) or key not in container:
        reasons.append(f"缺字段: {key}")
        return False
    if non_empty and not container.get(key):
        reasons.append(f"字段为空: {key}")
        return False
    return True


# ───────────────────────── CP-1 用例转操作 ─────────────────────────

def validate_spec(artifact: Any) -> CheckResult:
    """
    校验"用例转操作"产物(exec_spec)。

    结构:{"exec_spec": {case_id, mode, verify_status, assertions/ui/request ...}}
    通过条件(确定性、零业务):
      1. 带 case_id;
      2. mode 属于已知执行方式 {reconcile, api, ui, manual};
      3. verify_status == human_verified(人审后才允许进执行,防模型猜测);
      4. 至少有一处可判定依据(assertions 或 ui 或 request 非空);
      5. needs_review 为空(还有待补项不得过闸)。
    """
    reasons: list[str] = []
    spec = artifact.get("exec_spec") if isinstance(artifact, dict) else None
    if not isinstance(spec, dict):
        return CheckResult(STAGE_SPEC, StageVerdict.REJECT, ["产物缺 exec_spec 对象"],
                           artifact_hash(artifact))

    _require(spec, "case_id", reasons, non_empty=True)

    mode = spec.get("mode", "")
    if mode not in {"reconcile", "api", "ui", "manual"}:
        reasons.append(f"未知执行方式 mode={mode!r}")

    if spec.get("verify_status") != "human_verified":
        reasons.append(f"verify_status 非 human_verified(当前 {spec.get('verify_status')!r})")

    has_basis = bool(spec.get("assertions")) or bool(spec.get("ui")) or bool(spec.get("request"))
    if not has_basis:
        reasons.append("无可判定依据(assertions/ui/request 均空)")

    needs = spec.get("needs_review") or []
    if needs:
        reasons.append(f"仍有待补项 needs_review={needs}")

    verdict = StageVerdict.PASS if not reasons else StageVerdict.REJECT
    return CheckResult(STAGE_SPEC, verdict, reasons, artifact_hash(artifact))


# ───────────────────────── CP-2 UI 操作 ─────────────────────────

def validate_actions(artifact: Any) -> CheckResult:
    """
    校验"UI 操作"产物(actions)。

    结构:{"actions": {status, steps:[{index, kind, from_spec, ...}], evidence:[...], safety:{...}}}
    通过条件(确定性、零业务):
      1. status 不是终态异常(非 safety_blocked / error);
      2. steps 非空且每步带 index 与 from_spec(可回溯到 spec 的来源);
      3. evidence 非空(至少一条截图/录屏等证据路径);
      4. 无 safety.blocked 标记。
    """
    reasons: list[str] = []
    actions = artifact.get("actions") if isinstance(artifact, dict) else None
    if not isinstance(actions, dict):
        return CheckResult(STAGE_ACTIONS, StageVerdict.REJECT, ["产物缺 actions 对象"],
                           artifact_hash(artifact))

    status = actions.get("status", "")
    if status in {"safety_blocked", "error"}:
        reasons.append(f"执行终态异常 status={status!r}")

    steps = actions.get("steps")
    if not isinstance(steps, list) or not steps:
        reasons.append("steps 为空:未产生任何操作")
    else:
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                reasons.append(f"steps[{i}] 不是对象")
                continue
            if "index" not in step:
                reasons.append(f"steps[{i}] 缺 index")
            if not step.get("from_spec"):
                reasons.append(f"steps[{i}] 缺 from_spec(无法回溯到 exec_spec)")

    evidence = actions.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        reasons.append("evidence 为空:无截图/录屏证据")

    safety = actions.get("safety") or {}
    if isinstance(safety, dict) and safety.get("blocked"):
        reasons.append(f"命中安全阻断: {safety.get('reason', '')}")

    verdict = StageVerdict.PASS if not reasons else StageVerdict.REJECT
    return CheckResult(STAGE_ACTIONS, verdict, reasons, artifact_hash(artifact))


# ───────────────────────── CP-3 操作后验证 ─────────────────────────

def validate_evidence(artifact: Any) -> CheckResult:
    """
    校验"操作后验证"产物(evidence)。

    结构:{"evidence": {verdict, sources:{ui,api,db:bool}, evidence_sha256:{path:hash},
                       reconcile:{consistent, ...}}}
    通过条件(确定性、零业务):
      1. 带 verdict(本段给出的判定);
      2. sources 三源(ui/api/db)声明齐,且至少两源取到(单源无法交叉核对);
      3. evidence_sha256 非空,且每条都有哈希值(任何自动结论都必须有证据哈希);
      4. 若带 reconcile,则 reconcile.consistent 必须是布尔(有结论,不能悬空)。
    """
    reasons: list[str] = []
    ev = artifact.get("evidence") if isinstance(artifact, dict) else None
    if not isinstance(ev, dict):
        return CheckResult(STAGE_EVIDENCE, StageVerdict.REJECT, ["产物缺 evidence 对象"],
                           artifact_hash(artifact))

    _require(ev, "verdict", reasons, non_empty=True)

    sources = ev.get("sources")
    if not isinstance(sources, dict):
        reasons.append("缺 sources(三源声明)")
    else:
        for name in ("ui", "api", "db"):
            if name not in sources:
                reasons.append(f"sources 缺声明: {name}")
        got = sum(1 for name in ("ui", "api", "db") if sources.get(name))
        if got < 2:
            reasons.append(f"仅 {got} 源取到,无法交叉核对(至少需 2 源)")

    shas = ev.get("evidence_sha256")
    if not isinstance(shas, dict) or not shas:
        reasons.append("evidence_sha256 为空:自动结论缺证据哈希")
    else:
        for path, digest in shas.items():
            if not digest:
                reasons.append(f"证据无哈希: {path}")

    reconcile = ev.get("reconcile")
    if reconcile is not None:
        if not isinstance(reconcile, dict) or not isinstance(reconcile.get("consistent"), bool):
            reasons.append("reconcile.consistent 悬空(对账无明确结论)")

    verdict = StageVerdict.PASS if not reasons else StageVerdict.REJECT
    return CheckResult(STAGE_EVIDENCE, verdict, reasons, artifact_hash(artifact))


# 段 -> 校验器 的注册表(orchestrator 按段取用)。
VALIDATORS: dict[str, Callable[[Any], CheckResult]] = {
    STAGE_SPEC: validate_spec,
    STAGE_ACTIONS: validate_actions,
    STAGE_EVIDENCE: validate_evidence,
}


def validate(stage: str, artifact: Any) -> CheckResult:
    """按段名派发到对应校验器。未知段直接打回。"""
    validator = VALIDATORS.get(stage)
    if validator is None:
        return CheckResult(stage, StageVerdict.REJECT, [f"未知阶段: {stage}"], artifact_hash(artifact))
    return validator(artifact)


# ─────────────────── CP-1' 语义软门(旁路,不进 REJECT 流) ───────────────────
# 软门:checker 产 spec_review 候选,此函数给出可读判定供报告/人审用。
# 它【永不】让流水线 REJECT——只把"语义存疑"标注出来,信不信由人审。
REVIEW_ARTIFACT = "spec_review"
SEMANTIC_OK = "semantic_ok"
SEMANTIC_REVIEW = "needs_human_review"


def read_spec_semantics(artifact: Any) -> CheckResult:
    """读 spec_review 产物,翻成 CheckResult(仅表达 OK/存疑,不用于阻断)。

    用途:报告渲染、--plan-only/--dump 展示"这条用例转得忠不忠实"。
    verdict=PASS 表示语义 OK;verdict=REJECT 这里只代表"存疑待人审",调用方【不得】
    据此停流水线(软门语义见 orchestrator:只附提示、不改过闸结论)。
    """
    review = artifact.get(REVIEW_ARTIFACT) if isinstance(artifact, dict) else None
    if not isinstance(review, dict):
        return CheckResult(STAGE_SPEC, StageVerdict.PASS, ["无语义复核产物(未开 checker)"],
                           artifact_hash(artifact))
    status = review.get("status")
    reasons = list(review.get("reasons") or [])
    verdict = StageVerdict.PASS if status == SEMANTIC_OK else StageVerdict.REJECT
    return CheckResult(STAGE_SPEC, verdict, reasons, artifact_hash(artifact))
