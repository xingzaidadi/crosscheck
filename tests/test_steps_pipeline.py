"""统一 SetupStep 协议 验证(离线、零环境):有序步骤流水线 _phase_pipeline——
造数/主动作/审批视作同一种"步",按声明序执行,审批可落在主动作前后任意位置
(解除"审批必须在主动作之后"的写死约束)。用假 db/adapter/guard 注入,毫秒级。
跑:python tests/test_steps_pipeline.py
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import _WriteCtx, _phase_pipeline, _run_approve  # noqa: E402
from core.interfaces import Expected, TestCase, Verdict  # noqa: E402


class FakeDB:
    def query(self, sql, params=None):
        return [{"v": None}]


class FakeGuard:
    def __init__(self, trace):
        self.trace = trace
    def snapshot_before(self, expected):
        self.trace.append("snapshot_before")
    def snapshot_after(self, expected, marker):
        return Verdict.PASS, []


class FakeAdapter:
    """记录每步调用到共享 trace;perform=主动作,call=造数/审批。"""
    def __init__(self, trace):
        self.trace = trace
        self.base_url = ""
    def setup(self, case=None):
        pass
    def teardown(self):
        pass
    def _render(self, body, vars):
        return body
    def perform(self, case, marker, vars):
        self.trace.append("action")
        return SimpleNamespace(ok=True, api_status=200,
                               api_body={"code": 0, "data": {"code": "DOC1", "businessKey": "BK1"}})
    def call(self, step, vars):
        url = step.get("url", "?")
        self.trace.append(url)
        # 审批接口回 code=0;造数接口回占位
        return SimpleNamespace(ok=True, api_status=200, error=None,
                               api_body={"code": 0, "data": {"ok": True}})


def _mk_ctx(trace, steps):
    case = TestCase(case_id="TCX", feature="f", account_ref="", data_prep=None, steps=[],
                    expected=Expected(page=[], db=[], allowed_tables=[]),
                    raw={"steps": steps, "request": {"method": "POST", "url": "/main"}})
    return _WriteCtx(
        spec=SimpleNamespace(case_id="TCX", session=""), case=case, db=FakeDB(),
        adapter=FakeAdapter(trace), guard=FakeGuard(trace), verifier=None,
        marker="AUTOTEST_X", req={"method": "POST", "url": "/main"},
        code_path="data.code", base_url="", session_file="", vars={"marker": "AUTOTEST_X"})


def main():
    print("统一 SetupStep 协议 验证:\n")

    # 1) 审批落在主动作『之后』但『造数B 之前』——老式固定序(data_prep→action→approve)表达不出
    trace = []
    steps = [
        {"kind": "setup", "method": "POST", "url": "/setup/a"},
        {"kind": "action"},
        {"kind": "approve", "method": "POST", "url": "/bpm/approve",
         "business_key_from": {"response": "data.businessKey"},
         "expect": {"body": {"code": 0}}},
        {"kind": "setup", "method": "POST", "url": "/setup/b"},
    ]
    c = _mk_ctx(trace, steps)
    _phase_pipeline(c)
    assert trace == ["/setup/a", "snapshot_before", "action", "/bpm/approve", "/setup/b"], trace
    print("    ✓ 按声明序执行:造数A → 主动作 → 审批 → 造数B(审批夹在动作与造数B之间)")

    # 2) 审批在主动作后执行,拿得到动作响应里的 businessKey(action 先于 approve)
    assert c.bk == "BK1", c.bk
    assert any(l.get("name") == "BPM 审批" and l.get("ok") for l in c.layers), c.layers
    print(f"    ✓ 审批取到主动作响应的 businessKey={c.bk},响应校验通过")

    # 3) 审批『前置』于主动作:approve 在 action 之前,此时无 action 响应,businessKey 落空但不崩
    trace2 = []
    steps2 = [
        {"kind": "approve", "method": "POST", "url": "/bpm/pre",
         "business_key_from": {"response": "data.businessKey"}},
        {"kind": "action"},
    ]
    c2 = _mk_ctx(trace2, steps2)
    _phase_pipeline(c2)
    assert trace2 == ["/bpm/pre", "snapshot_before", "action"], trace2
    print("    ✓ 审批可前置于主动作(约束已解除):approve→action 顺序被如实执行")

    # 4) 纯造数流水线(无 action):不触发前置快照,只跑造数步
    trace3 = []
    c3 = _mk_ctx(trace3, [{"url": "/setup/x"}, {"url": "/setup/y"}])
    _phase_pipeline(c3)
    assert trace3 == ["/setup/x", "/setup/y"], trace3
    print("    ✓ 无 action 的纯造数流水线:按序跑,不触发前置快照")

    print("\n全部通过 ✅  —— 造数/主动作/审批统一为有序『步』,审批不再被写死在主动作之后")


if __name__ == "__main__":
    main()
