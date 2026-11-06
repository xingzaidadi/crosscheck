"""
保序并发池 验证(离线):结果与输入同序(不受完成先后影响);异常可隔离不中断其它。
批量执行里只读类并发提速就靠它;写入/UI 仍由 run_batch 串行调度。

跑:python tests/test_parallel.py
"""
from __future__ import annotations

import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.parallel import run_pool  # noqa: E402


def main():
    print("保序并发池 验证:\n")

    # 1) 保序:先完成的是小 n,但结果仍按输入顺序
    items = [5, 1, 3, 2, 4]
    def slow(n):
        time.sleep(n * 0.02)
        return n * 10
    t0 = time.time()
    out = run_pool(items, slow, workers=5)
    dur = time.time() - t0
    assert out == [50, 10, 30, 20, 40], out
    print(f"    ✓ 并发结果保序: {out}(耗时 {dur:.2f}s,远小于串行 {sum(items)*0.02:.2f}s)")

    # 2) workers=1 退化为顺序,结果一致
    assert run_pool(items, slow, workers=1) == [50, 10, 30, 20, 40]
    print("    ✓ workers=1 退化为顺序,结果一致")

    # 3) 异常隔离:capture 模式下坏项放异常,其它照常
    def maybe(n):
        if n == 3:
            raise ValueError("boom")
        return n
    res = run_pool([1, 2, 3, 4], maybe, workers=4, on_error="capture")
    assert res[0] == 1 and res[1] == 2 and res[3] == 4 and isinstance(res[2], ValueError), res
    print("    ✓ 异常隔离: 坏项放异常对象,其它项不受影响")
    print("\n全部通过 ✅  —— 保序并发池就位(只读类并发提速,写入仍串行)")


if __name__ == "__main__":
    main()
