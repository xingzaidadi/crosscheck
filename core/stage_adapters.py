"""
真实适配器:把现有三模块产出"翻译"成三段式契约产物(通用、零业务)。

  spec 段      core.modeler.model_case / spec.from_raw   -> {"exec_spec": {...}}
  actions 段   core.ui_agent.runtime.AgentRuntime.run    -> {"actions": {...}}
  evidence 段  core.verifier / core.reconciler 的结果     -> {"evidence": {...}}

设计:
  - 适配器不直接 import 浏览器/DB 等重依赖;重对象(page、runtime、db、建模入参)
    由构造时注入或以可调用形式传入,保证纯逻辑可测、可离线跑。
  - 适配器只做"结构翻译 + 证据哈希",不改判定、不认业务词。
  - 产出严格落在本段产物键内(配合 stage_runner 的写作用域门禁)。
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from core.stage_runner import StageContext


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj):
        return asdict(obj)
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return dict(getattr(obj, "__dict__", {}) or {})


def _file_sha256(path: str) -> str:
    """证据文件哈希;文件不存在/读失败返回空串(交给契约判定其缺失)。"""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _sha_map(paths: list[str]) -> dict[str, str]:
    return {path: _file_sha256(path) for path in paths if path}


# ───────────────────────── spec 段适配器 ─────────────────────────

class SpecAgent:
    """
    用例转操作:用注入的 modeler 把一条用例建模成 ExecSpec,翻译为 exec_spec 产物。

    modeler(context) -> ExecSpec | dict:
        调用方负责把 RawCase + routes/kb 等绑定进 modeler 闭包;本类只做翻译。
    auto_verify: 建模产物默认 draft;若调用方已走人审流程,可传 True 置 human_verified。
        (默认 False —— 不替人盖"已审"章,契约会据此打回,符合"人审后才进执行"。)
    """

    def __init__(self, modeler: Callable[[StageContext], Any], *, auto_verify: bool = False) -> None:
        self._modeler = modeler
        self._auto_verify = auto_verify

    def produce(self, stage: str, context: StageContext) -> dict[str, Any]:
        spec = _as_dict(self._modeler(context))
        if self._auto_verify and spec.get("verify_status") != "human_verified":
            spec["verify_status"] = "human_verified"
        spec.setdefault("case_id", context.case_id)
        return {"exec_spec": spec}


# ───────────────────────── actions 段适配器 ─────────────────────────

_UI_STATUS_OK = {"PASSED", "INCONCLUSIVE", "RUNNING"}
_UI_STATUS_SAFE_BLOCK = {"BLOCKED"}


class ActionsAgent:
    """
    UI 操作:用注入的 runner 执行 ExecSpec 的 ui 计划,翻译 AgentRuntimeResult 为 actions 产物。

    runner(exec_spec, context) -> AgentRuntimeResult | dict(含 status/actions/assertions/evidence/error)
    每个动作步补上 from_spec(回溯锚点),满足 CP-2 契约"可回溯"要求。
    """

    def __init__(self, runner: Callable[[dict[str, Any], StageContext], Any]) -> None:
        self._runner = runner

    def produce(self, stage: str, context: StageContext) -> dict[str, Any]:
        exec_spec = context.upstream_artifact("spec")
        raw = _as_dict(self._runner(exec_spec, context))
        status = raw.get("status", "")
        error = raw.get("error", "")

        steps: list[dict[str, Any]] = []
        for index, action in enumerate(raw.get("actions") or []):
            row = dict(action) if isinstance(action, dict) else {"value": action}
            row.setdefault("index", index)
            row.setdefault("kind", row.get("action") or row.get("kind") or "action")
            # from_spec:优先用动作自带 target/selector,否则落到 ui 计划的序号锚点
            if not row.get("from_spec"):
                row["from_spec"] = row.get("target") or row.get("selector") or f"ui.actions[{index}]"
            steps.append(row)

        evidence = [path for path in (raw.get("evidence") or []) if path]

        blocked = status in _UI_STATUS_SAFE_BLOCK
        if blocked:
            norm_status = "safety_blocked"
        elif error and not steps:
            norm_status = "error"
        else:
            norm_status = "ok"

        actions = {
            "status": norm_status,
            "raw_status": status,
            "steps": steps,
            "assertions": raw.get("assertions") or [],
            "evidence": evidence,
            "evidence_sha256": _sha_map(evidence),
            "safety": {"blocked": blocked, "reason": error if blocked else ""},
            "error": error,
        }
        return {"actions": actions}


# ───────────────────────── evidence 段适配器 ─────────────────────────

class EvidenceAgent:
    """
    操作后验证:汇集校验/对账结果 + actions 证据,翻译为 evidence 产物(三源对账)。

    verify(exec_spec, actions, context) -> dict,约定返回:
        {verdict:str, sources:{ui,api,db:bool}, reconcile:{consistent, ...}(可选),
         evidence:[path...](可选,额外证据), details:[...](可选)}
    本类把 actions 段已有证据哈希并入,保证"任何自动结论都有证据哈希"。
    """

    def __init__(self, verify: Callable[[dict[str, Any], dict[str, Any], StageContext], dict[str, Any]]) -> None:
        self._verify = verify

    def produce(self, stage: str, context: StageContext) -> dict[str, Any]:
        exec_spec = context.upstream_artifact("spec")
        actions = context.upstream_artifact("actions")
        result = _as_dict(self._verify(exec_spec, actions, context))

        sources = result.get("sources") or {}
        sources = {"ui": bool(sources.get("ui")), "api": bool(sources.get("api")),
                   "db": bool(sources.get("db"))}

        # 证据哈希:并上游 actions 证据 + 本段额外证据
        sha = dict(actions.get("evidence_sha256") or {})
        sha.update(_sha_map(result.get("evidence") or []))

        evidence = {
            "verdict": result.get("verdict", ""),
            "sources": sources,
            "evidence_sha256": sha,
            "details": result.get("details") or [],
        }
        if result.get("reconcile") is not None:
            evidence["reconcile"] = _as_dict(result["reconcile"])
        return {"evidence": evidence}


def reconcile_to_sources(reconcile: Any, *, ui: bool) -> dict[str, bool]:
    """便捷:由 ReconcileResult(接口 vs 库)推三源可得性。接口+库各算一源,ui 由调用方给。"""
    data = _as_dict(reconcile)
    api = data.get("api_total") is not None
    db = data.get("db_total") is not None or data.get("table")
    return {"ui": bool(ui), "api": bool(api), "db": bool(db)}
