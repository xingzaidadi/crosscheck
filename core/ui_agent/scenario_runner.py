"""场景执行闭环驱动器:把 scenario_execution_drafts 的草稿逐条只读真跑、分别报告。

兑现审计建议 #3 的最后一步——此前 scenario_execution_drafts 只产"可执行草稿"(draft),
没有任何 runner 真正逐条执行并分别报告。本模块补上这一步,且严守铁律:

  · read-only 优先:只执行 state=="draft" 的只读场景;写操作场景(needs_authorization)
    一律**不执行**,只在矩阵里标 SKIPPED_NEEDS_AUTH(与 risk_policy=read_only 双保险)。
  · 不自动晋级 / 不伪造:verdict 直接取自 AgentRuntime.run 的真实判定,本模块不改判。
  · 零业务:只认 scenario_execution_drafts 产出的通用场景 id,不认任何业务词。
  · 异常隔离:单条场景抛错不连累其余(记 ENV_ERROR + reason)。

复用:build_agent_plan(带 oracles 的完整 plan)、AgentRuntime.run(真实执行+判定)。
不新造计划或判定逻辑。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def run_scenarios(
    *,
    page,
    request: Any,
    scenario_drafts: list[dict[str, Any]],
    run_dir: str | Path,
    runtime_factory: Callable[[], Any],
    plan_builder: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    """逐条执行场景草稿,各产独立证据与判定,汇总覆盖矩阵。

    参数:
      page            : 已登录的 playwright page(调用方在同一 context 建好,复用登录态)。
      request         : AgentTestRequest,携带 url / instruction / role / risk_policy。
      scenario_drafts : scenario_execution_drafts(request) 的产物。
      run_dir         : 本次运行根目录;每场景在 run_dir/scenarios/<sid>/evidence 下独立产证。
      runtime_factory : 无参工厂,返回一个 AgentRuntime(policy/allow_write 由调用方绑定)。
      plan_builder    : 可注入的建计划函数(测试用桩);缺省用 build_agent_plan。

    返回覆盖矩阵 dict。
    """
    root = Path(run_dir)
    scen_dir = root / "scenarios"

    if plan_builder is None:
        from core.agent_test_intake import AgentTestRequest, build_agent_plan

        def plan_builder(instruction: str):  # type: ignore[misc]
            return build_agent_plan(AgentTestRequest(
                url=str(getattr(request, "url", "") or ""),
                instruction=instruction,
                role=str(getattr(request, "role", "default") or "default"),
                risk_policy=str(getattr(request, "risk_policy", "read_only") or "read_only"),
            ))

    rows: list[dict[str, Any]] = []
    for draft in scenario_drafts:
        sid = str(draft.get("scenario") or "")
        title = draft.get("title")
        state = draft.get("state")

        # 写操作场景:绝不自动执行,只标记需人审授权。
        if state == "needs_authorization":
            rows.append({"scenario": sid, "title": title, "verdict": "SKIPPED_NEEDS_AUTH",
                         "executed": False,
                         "reason": draft.get("reason") or "写操作场景需显式人审授权,不自动执行"})
            continue
        # 建模阶段就失败的草稿:不执行,如实记录。
        if state == "draft_failed":
            rows.append({"scenario": sid, "title": title, "verdict": "DRAFT_FAILED",
                         "executed": False, "reason": draft.get("reason") or "场景建模失败"})
            continue
        if state != "draft":
            rows.append({"scenario": sid, "title": title, "verdict": "SKIPPED_UNKNOWN_STATE",
                         "executed": False, "reason": f"未知草稿状态:{state!r}"})
            continue

        instruction = str(draft.get("instruction") or "")
        evidence_dir = scen_dir / (sid or "scenario") / "evidence"
        try:
            plan = plan_builder(instruction)
            # 边界场景的结构化可观察 oracle 由 scenario_execution_drafts 附在草稿上;
            # plan_builder 只从指令文本重建计划,拿不到这些结构化断言,故在此并入计划的
            # oracles(去重),让 empty_query/not_found/reset_filter 真正带着可判断言执行。
            draft_oracles = list(draft.get("oracles") or [])
            if draft_oracles and hasattr(plan, "oracles"):
                existing = list(getattr(plan, "oracles") or [])
                for extra in draft_oracles:
                    if not any(o.get("kind") == extra.get("kind")
                               and str(o.get("value")) == str(extra.get("value"))
                               for o in existing):
                        existing.append(dict(extra))
                plan.oracles = existing
            # 回到场景起点再跑(确定性、只读);goto 失败不阻断,交给 runtime 内部处理。
            try:
                page.goto(getattr(plan, "url", "") or str(getattr(request, "url", "")),
                          wait_until="domcontentloaded", timeout=20000)
            except Exception:
                pass
            runtime = runtime_factory()
            execution = runtime.run(page, plan, evidence_dir)
            exec_dict = execution.to_dict() if hasattr(execution, "to_dict") else dict(execution)
            assertions = exec_dict.get("assertions") or []
            rows.append({
                "scenario": sid,
                "title": title,
                "instruction": instruction,
                "verdict": exec_dict.get("status", "INCONCLUSIVE"),
                "executed": True,
                "assertions": [
                    {"kind": a.get("kind"), "target": a.get("target") or a.get("value"),
                     "expected": a.get("expected"), "actual": a.get("actual"),
                     "passed": a.get("passed")}
                    for a in assertions
                ],
                "assertions_total": len(assertions),
                "assertions_passed": sum(1 for a in assertions if a.get("passed") is True),
                "evidence_dir": str(evidence_dir),
                "error": exec_dict.get("error") or "",
            })
        except Exception as exc:  # noqa: BLE001  单条场景异常不连累其余
            rows.append({"scenario": sid, "title": title, "verdict": "ENV_ERROR",
                         "executed": True, "instruction": instruction,
                         "evidence_dir": str(evidence_dir), "error": str(exc)[:300]})

    counts: dict[str, int] = {}
    for row in rows:
        verdict = row.get("verdict") or "UNKNOWN"
        counts[verdict] = counts.get(verdict, 0) + 1
    executed = sum(1 for row in rows if row.get("executed"))
    return {
        "total": len(rows),
        "executed": executed,
        "skipped_needs_auth": sum(1 for r in rows if r.get("verdict") == "SKIPPED_NEEDS_AUTH"),
        "counts": counts,
        "scenarios": rows,
    }
