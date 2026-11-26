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


def main():
    print("Tier-2 场景执行闭环 骨架回归:\n")
    test_read_only_scenarios_become_executable_drafts()
    test_write_scenario_is_not_auto_expanded()
    test_empty_instruction_degrades_gracefully()
    print("\n全部通过 ✅  —— 场景建议→执行草稿闭环接线正确,read-only 优先、写操作需人审")


if __name__ == "__main__":
    main()
