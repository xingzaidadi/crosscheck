"""场景执行闭环驱动器的离线回归(纯逻辑 + 零浏览器桩)。

验证审计建议 #3 的最后一步真的接通:scenario_execution_drafts 产出的草稿,
run_scenarios 能逐条只读执行、分别报告,且:
  · 写操作场景绝不被执行(SKIPPED_NEEDS_AUTH),不调用 runtime;
  · draft_failed 不执行;
  · 单条场景异常被隔离,不连累其余;
  · 覆盖矩阵 total/executed/counts 正确。

纯逻辑,无需真实后端、无需 chromium。跑:python tests/test_scenario_runner.py
"""
from __future__ import annotations

import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ui_agent.scenario_runner import run_scenarios  # noqa: E402
from core.ui_agent.capabilities import scenario_execution_drafts  # noqa: E402


class _FakeRequest:
    def __init__(self, instruction, url="https://example.test/list", role="default"):
        self.instruction = instruction
        self.url = url
        self.role = role
        self.risk_policy = "read_only"


class _FakePage:
    """记录 goto 调用;永不发真网络。"""
    def __init__(self):
        self.gotos = []

    def goto(self, url, **kwargs):
        self.gotos.append(url)


class _FakePlan:
    def __init__(self, url="https://example.test/list"):
        self.url = url


class _FakeRuntime:
    """桩:按注入的 status 返回 execution,记录被调用次数。"""
    calls = 0

    def __init__(self, status="PASSED", assertions=None):
        self._status = status
        self._assertions = assertions or [{"kind": "visibility", "target": "列表",
                                           "expected": True, "actual": True, "passed": True}]

    def run(self, page, plan, evidence_dir):
        _FakeRuntime.calls += 1
        return {"status": self._status, "assertions": self._assertions, "error": "",
                "evidence": [str(evidence_dir)]}


def _drafts():
    return [
        {"scenario": "happy_path", "title": "主流程", "state": "draft",
         "instruction": "查询订单列表", "actions": [{"action": "observe"}], "oracles": []},
        {"scenario": "not_found", "title": "不存在的数据", "state": "draft",
         "instruction": "查询订单列表;用不存在的数据", "actions": [{"action": "observe"}], "oracles": []},
        {"scenario": "mutation_review", "title": "写操作（需显式授权）",
         "state": "needs_authorization", "plan": None,
         "reason": "写操作场景需显式人审授权,不自动展开成可执行草稿"},
    ]


def test_wiring_drafts_from_broad_instruction():
    """接线:含『查询/审批』的宽指令应展开 ≥4 条 read_only draft + 写场景 needs_auth。"""
    drafts = scenario_execution_drafts(_FakeRequest("查询并审批订单列表"))
    states = [d.get("state") for d in drafts]
    draft_count = states.count("draft")
    assert draft_count >= 4, f"应至少 4 条可执行只读草稿,实得 {draft_count}:{states}"
    assert "needs_authorization" in states, f"写操作场景应标 needs_authorization:{states}"
    print(f"    ✓ 宽指令展开 {draft_count} 条只读草稿 + 写场景需授权(接线正确)")


def test_run_scenarios_executes_drafts_skips_write():
    """核心:只读草稿逐条执行,写场景跳过且不调用 runtime。"""
    _FakeRuntime.calls = 0
    page = _FakePage()
    with tempfile.TemporaryDirectory() as tmp:
        matrix = run_scenarios(
            page=page, request=_FakeRequest("查询订单列表"),
            scenario_drafts=_drafts(), run_dir=tmp,
            runtime_factory=lambda: _FakeRuntime("PASSED"),
            plan_builder=lambda instruction: _FakePlan(),
        )
    assert matrix["total"] == 3, matrix["total"]
    assert matrix["executed"] == 2, f"应只执行 2 条只读草稿:{matrix}"
    assert matrix["skipped_needs_auth"] == 1, matrix
    assert _FakeRuntime.calls == 2, f"runtime 应只被 2 条只读草稿调用,写场景不得触发:{_FakeRuntime.calls}"
    verdicts = {r["scenario"]: r["verdict"] for r in matrix["scenarios"]}
    assert verdicts["happy_path"] == "PASSED", verdicts
    assert verdicts["mutation_review"] == "SKIPPED_NEEDS_AUTH", verdicts
    # 写场景绝不被 goto(根本没进执行分支)
    assert len(page.gotos) == 2, f"只读场景各 goto 一次,写场景不 goto:{page.gotos}"
    print("    ✓ 只读草稿逐条真执行、各自判定;写场景跳过且绝不触发 runtime/goto")


def test_run_scenarios_counts_and_separate_evidence():
    """覆盖矩阵 counts 正确,且每场景 evidence 目录独立。"""
    _FakeRuntime.calls = 0
    with tempfile.TemporaryDirectory() as tmp:
        # happy_path PASSED,not_found FAILED → counts 应分开计
        def factory():
            factory.i += 1
            return _FakeRuntime("PASSED" if factory.i == 1 else "FAILED")
        factory.i = 0
        matrix = run_scenarios(
            page=_FakePage(), request=_FakeRequest("查询订单列表"),
            scenario_drafts=_drafts(), run_dir=tmp,
            runtime_factory=factory, plan_builder=lambda instruction: _FakePlan(),
        )
    assert matrix["counts"].get("PASSED") == 1, matrix["counts"]
    assert matrix["counts"].get("FAILED") == 1, matrix["counts"]
    assert matrix["counts"].get("SKIPPED_NEEDS_AUTH") == 1, matrix["counts"]
    dirs = [r.get("evidence_dir") for r in matrix["scenarios"] if r.get("executed")]
    assert len(dirs) == len(set(dirs)) == 2, f"两条执行场景应各自独立 evidence 目录:{dirs}"
    assert "happy_path" in dirs[0] and "not_found" in dirs[1], dirs
    print("    ✓ 覆盖矩阵 counts 分列、每场景 evidence 目录物理独立")


def test_run_scenarios_isolates_exception():
    """单条场景抛错被隔离为 ENV_ERROR,不连累其余。"""
    class _BoomRuntime:
        def run(self, page, plan, evidence_dir):
            raise RuntimeError("boom")

    drafts = [
        {"scenario": "happy_path", "title": "主流程", "state": "draft", "instruction": "x"},
        {"scenario": "not_found", "title": "空态", "state": "draft", "instruction": "y"},
    ]
    toggle = {"n": 0}

    def factory():
        toggle["n"] += 1
        return _BoomRuntime() if toggle["n"] == 1 else _FakeRuntime("PASSED")

    with tempfile.TemporaryDirectory() as tmp:
        matrix = run_scenarios(
            page=_FakePage(), request=_FakeRequest("查询订单列表"),
            scenario_drafts=drafts, run_dir=tmp,
            runtime_factory=factory, plan_builder=lambda instruction: _FakePlan(),
        )
    verdicts = {r["scenario"]: r["verdict"] for r in matrix["scenarios"]}
    assert verdicts["happy_path"] == "ENV_ERROR", verdicts
    assert verdicts["not_found"] == "PASSED", f"首条异常不应连累次条:{verdicts}"
    print("    ✓ 单条场景异常被隔离(ENV_ERROR),其余照常执行")


def test_draft_failed_not_executed():
    """draft_failed 的草稿不被执行。"""
    _FakeRuntime.calls = 0
    drafts = [{"scenario": "bad", "title": "建模失败", "state": "draft_failed", "reason": "x"}]
    with tempfile.TemporaryDirectory() as tmp:
        matrix = run_scenarios(
            page=_FakePage(), request=_FakeRequest("查询"), scenario_drafts=drafts,
            run_dir=tmp, runtime_factory=lambda: _FakeRuntime(), plan_builder=lambda i: _FakePlan(),
        )
    assert matrix["executed"] == 0, matrix
    assert matrix["scenarios"][0]["verdict"] == "DRAFT_FAILED", matrix
    assert _FakeRuntime.calls == 0, "draft_failed 不得触发 runtime"
    print("    ✓ draft_failed 草稿不执行")


def main():
    print("场景执行闭环驱动器离线回归:\n")
    test_wiring_drafts_from_broad_instruction()
    test_run_scenarios_executes_drafts_skips_write()
    test_run_scenarios_counts_and_separate_evidence()
    test_run_scenarios_isolates_exception()
    test_draft_failed_not_executed()
    print("\n全部通过 ✅  —— 场景建议→逐条只读真跑→分别报告 闭环已接通(写场景永不自动执行)")


if __name__ == "__main__":
    main()
