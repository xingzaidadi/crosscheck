"""Tier-2 骨架回归:场景建议 → 执行闭环草稿(离线、零浏览器、零业务)。

审计建议 #3 要"把场景建议接进执行闭环"。本测试锁住框架骨架的接线正确性:
  - read_only 场景 → 确定性改写成可执行指令 → 复用 build_agent_plan 产出真实动作/断言草稿;
  - 草稿 draft 态、auto_executed=False(不自动跑,守"不自动晋级/read-only 优先"铁律);
  - 写操作场景(authorized_write)不展开成可执行草稿,仅标 needs_authorization(需人审);
  - 场景↔草稿一一对应,不吞不造。

离线只验"接线与不回退",不验"真跑通质量"——那依赖真实后端/真实理解,属第三档。

跑:python tests/test_scenario_execution_loop.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent_test_intake import AgentTestRequest  # noqa: E402
from core.ui_agent.capabilities import generate_scenarios, scenario_execution_drafts  # noqa: E402


def test_read_only_scenarios_become_executable_drafts():
    req = AgentTestRequest(url="https://example.test", instruction="测试订单列表查询")
    scenarios = generate_scenarios(req.instruction)
    drafts = scenario_execution_drafts(req)
    # 场景与草稿一一对应(不吞不造)
    assert len(drafts) == len(scenarios), (len(drafts), len(scenarios))
    assert {d["scenario"] for d in drafts} == {s["id"] for s in scenarios}
    read_only = [d for d in drafts if d["state"] == "draft"]
    assert read_only, "应至少有一条 read_only 执行草稿"
    for d in read_only:
        assert d["auto_executed"] is False, "草稿绝不自动执行(不自动晋级铁律)"
        assert isinstance(d["actions"], list) and d["actions"], f"草稿应有真实可执行动作:{d}"
        assert "instruction" in d and d["instruction"]
    print(f"    ✓ read_only 场景→可执行草稿({len(read_only)} 条),draft 态、不自动跑、动作非空")


def test_write_scenario_is_not_auto_expanded():
    req = AgentTestRequest(url="https://example.test", instruction="测试订单提交与审批流程")
    drafts = scenario_execution_drafts(req)
    write_drafts = [d for d in drafts if d.get("scenario") == "mutation_review"]
    assert write_drafts, "含提交/审批的指令应产生写操作场景"
    for d in write_drafts:
        assert d["state"] == "needs_authorization", d
        assert d["plan"] is None, "写场景不自动展开成可执行草稿,须人审授权"
    print("    ✓ 写操作场景不自动展开,标 needs_authorization(需显式人审授权)")


def test_empty_instruction_degrades_gracefully():
    req = AgentTestRequest(url="https://example.test", instruction="")
    drafts = scenario_execution_drafts(req)
    # 空指令至少产 happy_path 一条,不崩
    assert any(d["scenario"] == "happy_path" for d in drafts), drafts
    print("    ✓ 空指令优雅降级(至少主流程一条,不崩)")


def test_boundary_scenarios_carry_observable_oracles():
    """异常/边界场景(empty_query/not_found/reset_filter)应带**结构化可观察断言**。

    修复点:此前这三条场景的预期是散文("确认列表正常渲染"等),无法抽成断言,只会落进
    unresolved_expectations 把场景拖成 INCONCLUSIVE。改法后它们必须携带 runtime 已支持、
    能判 PASS/FAIL 的 oracle kind。本测试锁住这个属性,防回退。
    """
    req = AgentTestRequest(url="https://example.test", instruction="测试订单列表查询")
    drafts = {d["scenario"]: d for d in scenario_execution_drafts(req)}
    # runtime(scripts/ui_test.py::_evaluate_oracle)真正能判的、本修复用到的 kind 白名单
    judgeable = {"page_health", "filter_controls", "count", "text_contains", "visibility"}
    for sid in ("empty_query", "not_found", "reset_filter"):
        assert sid in drafts, f"宽查询指令应展开 {sid} 场景:{list(drafts)}"
        oracles = drafts[sid].get("oracles") or []
        kinds = {o.get("kind") for o in oracles}
        assert oracles, f"{sid} 应带可观察断言,而非空:{drafts[sid]}"
        assert kinds & judgeable, f"{sid} 的断言必须含 runtime 可判 kind,实得 {kinds}"
        # 指令尾句不再塞"确认 XX 正常/出现/被清空"这类无法判的散文
        instr = drafts[sid].get("instruction") or ""
        assert "确认列表" not in instr and "确认出现" not in instr and "确认条件" not in instr, \
            f"{sid} 指令不应再含散文预期:{instr!r}"
    # not_found 必须含 count=0 这个空结果硬信号
    nf_kinds = {o.get("kind") for o in drafts["not_found"]["oracles"]}
    assert "count" in nf_kinds, f"not_found 应含 count=0 硬信号:{nf_kinds}"
    print("    ✓ empty_query/not_found/reset_filter 均带结构化可观察断言(可判 PASS/FAIL,非散文)")


def main():
    print("Tier-2 场景执行闭环 骨架回归:\n")
    test_read_only_scenarios_become_executable_drafts()
    test_write_scenario_is_not_auto_expanded()
    test_empty_instruction_degrades_gracefully()
    test_boundary_scenarios_carry_observable_oracles()
    print("\n全部通过 ✅  —— 场景建议→执行草稿闭环接线正确,read-only 优先、写操作需人审")


if __name__ == "__main__":
    main()
