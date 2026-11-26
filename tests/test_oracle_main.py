"""core.oracle 真执行回归(main()+assert)。

补盲区:tests/test_oracle.py 是纯 pytest-fixture 风格(def test_(...) 无 main()),
run_tests.py 把它当子进程脚本跑时只 import 模块、断言体从不执行 = 假通过。
本文件把那 3 组断言搬成 run_tests.py 下真执行,锁住 oracle 的确定性判定行为。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.oracle import evaluate, evaluate_one, poll


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # 1) 嵌套路径 + 多算子(equals/gte/contains)全过。
    evidence = {"api": {"data": {"status": "PUBLISHED", "amount": 120}},
                "ui": {"text": "Published strategy"}}
    result = evaluate([
        {"id": "a1", "subject": "api.data.status", "operator": "equals",
         "expected": "PUBLISHED", "proof": "api"},
        {"id": "a2", "subject": "api.data.amount", "operator": "gte",
         "expected": 100, "proof": "api"},
        {"id": "a3", "subject": "ui.text", "operator": "contains",
         "expected": "strategy", "proof": "ui"},
    ], evidence)
    _assert(result["passed"] is True, "嵌套路径+equals/gte/contains 全过")
    print("[1] 嵌套路径 + equals/gte/contains 全过 ✓")

    # 2) 缺失值 not_equals 显式过;失败断言显式计入 failed。
    missing = evaluate_one(
        {"id": "a", "subject": "api.nope", "operator": "not_equals", "expected": "x"},
        {"api": {}})
    _assert(missing["passed"] is True, "缺失值 not_equals → passed(缺失≠x)")
    failed = evaluate(
        [{"id": "a", "subject": "api.code", "operator": "equals", "expected": 0}],
        {"api": {"code": 1}})
    _assert(failed["passed"] is False, "值不等 → 整体 fail")
    _assert(failed["failed"] == ["a"], "失败断言 id 显式计入 failed")
    print("[2] 缺失 not_equals 显式过 + 失败断言显式计入 failed ✓")

    # 3) poll 到 until 断言通过即停(第二轮证据 READY)。
    calls = {"count": 0}

    def evidence_supplier():
        calls["count"] += 1
        return {"api": {"status": "READY" if calls["count"] > 1 else "PENDING"}}

    polled = poll(
        [{"id": "ready", "subject": "api.status", "operator": "equals", "expected": "READY"}],
        evidence_supplier, until="ready", timeout_s=0.1, interval_s=0.01)
    _assert(polled["passed"] is True, "poll 到 READY 整体过")
    _assert(polled["until_passed"] is True, "until=ready 命中")
    print("[3] poll 到 until 断言通过即停 ✓")

    print("\nALL PASS · core.oracle 确定性判定(嵌套路径/多算子/缺失 not_equals/poll until)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
