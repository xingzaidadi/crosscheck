"""
三段式装配:把 SpecAgent/ActionsAgent/EvidenceAgent 的注入闭包接到真实组件
(routes/kb + Playwright page + DB),给出可落地的工厂(通用、零业务)。

分层:
  - make_spec_modeler(): 纯离线可跑。用 load_routes + model_case,把一条 RawCase 建模成 ExecSpec。
  - make_ui_runner():    惰性 import Playwright。按 exec_spec.ui 构造 AgentPlan,起浏览器执行。
  - make_evidence_verifier(): 汇集 UI 断言(+可选 DB 对账)为 evidence 结论。

重依赖(playwright / db)只在"执行闭包真正被调用"时才 import,
因此 spec 段(plan-only)可在无浏览器/无库环境离线验证。换业务只改 workspace。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from core.stage_runner import StageContext


# ───────────────────────── spec 段:建模闭包 ─────────────────────────

def make_spec_modeler(
    raw_by_case: dict[str, Any],
    *,
    routes: dict[str, Any],
    kb_root: Path,
    caps_root: Path,
    db: Any = None,
) -> Callable[[StageContext], Any]:
    """
    返回 modeler(context) -> ExecSpec。raw_by_case: {case_id: RawCase}。
    用现有 core.modeler.model_case 复用自发现产物,确定性建模。
    """
    from core.modeler import model_case

    def modeler(context: StageContext):
        raw = raw_by_case.get(context.case_id)
        if raw is None:
            raise KeyError(f"用例未找到: {context.case_id}")
        return model_case(raw, routes=routes, kb_root=kb_root, caps_root=caps_root, db=db)

    return modeler


# ───────────────────────── actions 段:UI 执行闭包 ─────────────────────────

def make_ui_runner(
    *,
    evidence_root: Path,
    session: str | None = None,
    headed: bool = False,
    risk_policy: str = "read_only",
    allow_write: bool = False,
    max_steps: int = 20,
) -> Callable[[dict[str, Any], StageContext], Any]:
    """
    返回 runner(exec_spec, context) -> AgentRuntimeResult。
    按 exec_spec.ui 组装自然语言指令 -> build_agent_plan -> AgentRuntime.run(page, ...)。
    Playwright 惰性 import:仅执行时需要浏览器。
    """
    def runner(exec_spec: dict[str, Any], context: StageContext):
        from playwright.sync_api import sync_playwright

        from core.agent_test_intake import AgentTestRequest, build_agent_plan
        from core.ui_agent.runtime import AgentRuntime

        ui = exec_spec.get("ui") or {}
        url = ui.get("page_url") or exec_spec.get("base_url") or ""
        if not url:
            raise ValueError(f"exec_spec.ui 无 page_url,无法执行 UI: {context.case_id}")
        instruction = ui.get("instruction") or exec_spec.get("title") or context.case_id

        request = AgentTestRequest(url=url, instruction=instruction,
                                   role=exec_spec.get("role", "default"),
                                   risk_policy=risk_policy, allow_write=allow_write,
                                   write_scope=exec_spec.get("write_scope", ""))
        plan = build_agent_plan(request)

        evidence_dir = Path(evidence_root) / context.case_id / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not headed)
            context_args = {"storage_state": session} if session else {}
            browser_context = browser.new_context(**context_args)
            page = browser_context.new_page()
            try:
                runtime = AgentRuntime(policy=risk_policy, allow_write=allow_write,
                                       write_scope=exec_spec.get("write_scope", ""),
                                       max_steps=max_steps)
                return runtime.run(page, plan, evidence_dir)
            finally:
                browser_context.close()
                browser.close()

    return runner


# ───────────────────────── evidence 段:验证闭包 ─────────────────────────

def make_evidence_verifier(
    *,
    db_factory: Callable[[], Any] | None = None,
) -> Callable[[dict[str, Any], dict[str, Any], StageContext], dict[str, Any]]:
    """
    返回 verify(exec_spec, actions, context) -> evidence 结论 dict。

    - UI 源:由 actions 段断言是否全过推定;
    - API/DB 源:若 exec_spec 声明 reconcile 映射且提供 db_factory,则做接口 vs 库对账;
      否则仅给 UI 结论(契约会据"至少 2 源"判是否过闸)。
    db_factory 惰性建库连接:无库环境下只要不走对账分支即可离线。
    """
    def verify(exec_spec: dict[str, Any], actions: dict[str, Any], context: StageContext) -> dict[str, Any]:
        assertions = actions.get("assertions") or []
        ui_ok = bool(assertions) and all(item.get("passed") is True for item in assertions)
        ui_got = bool(actions.get("steps"))

        details: list[str] = []
        sources = {"ui": ui_got, "api": False, "db": False}
        reconcile_out: dict[str, Any] | None = None
        verdict = "pass" if ui_ok else ("fail" if assertions else "inconclusive")

        recon_cfg = exec_spec.get("reconcile") or {}
        if recon_cfg and db_factory is not None:
            try:
                from core.reconciler import Reconciler

                db = db_factory()
                reconciler = Reconciler(db, recon_cfg.get("mapping") or {})
                result = reconciler.reconcile(recon_cfg.get("api_params") or {},
                                              recon_cfg.get("api_response") or {})
                reconcile_out = result.__dict__ if hasattr(result, "__dict__") else dict(result)
                sources["api"] = reconcile_out.get("api_total") is not None
                sources["db"] = (reconcile_out.get("db_total") is not None
                                 or bool(reconcile_out.get("table")))
                if not reconcile_out.get("consistent", True):
                    verdict = "fail"
                    details.append("接口与库对账不一致")
            except Exception as exc:  # noqa: BLE001
                details.append(f"对账执行异常: {exc}")

        out: dict[str, Any] = {"verdict": verdict, "sources": sources, "details": details}
        if reconcile_out is not None:
            out["reconcile"] = reconcile_out
        return out

    return verify


# ───────────────────────── 一站式装配 ─────────────────────────

def make_readonly_db_factory(db_name: str = ""):
    """Build a read-only DbClient factory from workspace/config/db.yaml.

    Returns None when no usable read-only DB is configured, so the evidence
    stage degrades to the UI source only instead of crashing.
    """
    from core.config import db_config, db_params

    cfg = db_config()
    chosen_name = db_name or cfg.get("default_readonly")
    params = db_params(chosen_name) if chosen_name else None
    dsn = (cfg.get("readonly") or {}).get("dsn", "")
    dsn = "" if (dsn and "TODO" in dsn) else dsn

    if not params and not dsn:
        return None

    def factory():
        from db.client import DbClient

        if params:
            return DbClient(readonly_params=params)
        return DbClient(dsn_readonly=dsn)

    return factory


def build_agents(
    raw_by_case: dict[str, Any],
    *,
    routes: dict[str, Any],
    kb_root: Path,
    caps_root: Path,
    evidence_root: Path,
    auto_verify: bool = False,
    session: str | None = None,
    headed: bool = False,
    allow_write: bool = False,
    db_factory: Callable[[], Any] | None = None,
    db_name: str = "",
) -> dict[str, Any]:
    """装配三段子 Agent(SpecAgent/ActionsAgent/EvidenceAgent),返回 orchestrator 可用的 mapping。"""
    from core.stage_adapters import ActionsAgent, EvidenceAgent, SpecAgent

    if db_factory is None and db_name:
        db_factory = make_readonly_db_factory(db_name)

    return {
        "spec": SpecAgent(make_spec_modeler(raw_by_case, routes=routes, kb_root=kb_root,
                                            caps_root=caps_root), auto_verify=auto_verify),
        "actions": ActionsAgent(make_ui_runner(evidence_root=evidence_root, session=session,
                                               headed=headed, allow_write=allow_write)),
        "evidence": EvidenceAgent(make_evidence_verifier(db_factory=db_factory)),
    }
