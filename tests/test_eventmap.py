"""异步事件口径自发现 验证(离线、零业务):假时钟 + 假计数模拟表在不同轮次冒出新行。
跑:python tests/test_eventmap.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.eventmap import learn_events, suggest_poll  # noqa: E402


def main():
    print("异步事件口径自发现 验证:\n")

    # 受控时钟:每次 sleep 推进时间与轮次;count_fn 据轮次让表在不同时刻冒行
    state = {"t": 0.0, "round": 0}
    base = {"t_node": 0, "t_assign": 0, "t_quiet": 5}

    def clock():
        return state["t"]

    def sleep(s):
        state["t"] += s
        state["round"] += 1

    def count_fn(table):
        r = state["round"]
        if table == "t_node" and r >= 1:
            return 1          # 第1轮(~2s)冒出
        if table == "t_assign" and r >= 2:
            return 1          # 第2轮(~4s)冒出
        return base[table]    # t_quiet 一直不变

    fired = {"n": 0}
    res = learn_events(["t_node", "t_assign", "t_quiet"], lambda: fired.__setitem__("n", 1),
                       count_fn=count_fn, sleep_fn=sleep, clock=clock,
                       interval_s=2, quiet_rounds=2, settle_s=100)

    assert fired["n"] == 1, "trigger_fn 应被调用"
    tb = res["tables"]
    assert tb["t_node"]["fired"] and tb["t_node"]["first_seen_s"] == 2, tb["t_node"]
    assert tb["t_assign"]["fired"] and tb["t_assign"]["first_seen_s"] == 4, tb["t_assign"]
    assert not tb["t_quiet"]["fired"], tb["t_quiet"]
    print(f"    ✓ t_node@2s、t_assign@4s 冒行;t_quiet 未冒(初值5不算事件)")

    sp = suggest_poll(res)
    assert sp["event_tables"] == ["t_assign", "t_node"], sp
    assert sp["learned_slowest_s"] == 4 and sp["timeout_s"] == 6, sp   # ceil(4*1.5)=6
    print(f"    ✓ 推等待口径: timeout={sp['timeout_s']}s, 事件表={sp['event_tables']}")

    # 全程无事件 → 空口径、下限 timeout
    state2 = {"t": 0.0, "round": 0}
    res2 = learn_events(["a", "b"], lambda: None,
                        count_fn=lambda t: 0, sleep_fn=lambda s: (state2.__setitem__("t", state2["t"] + s),
                                                                  state2.__setitem__("round", state2["round"] + 1)),
                        clock=lambda: state2["t"], interval_s=2, quiet_rounds=2, settle_s=100)
    sp2 = suggest_poll(res2)
    assert sp2["event_tables"] == [] and sp2["timeout_s"] == 6, sp2
    print("    ✓ 无事件 → 空事件表 + 下限 timeout")

    print("\n全部通过 ✅  —— 异步事件口径(哪些表、等多久)机器学出,零业务离线可测")


if __name__ == "__main__":
    main()
