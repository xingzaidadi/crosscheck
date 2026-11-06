"""
页面数值断言 验证(离线):页签/按钮计算值 == 库标量/字面量。

跑:python tests/test_ui_value.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ui_value import check_values, _num  # noqa: E402


class FakeDB:
    def __init__(self, n): self.n = n
    def query(self, sql): return [{"c": self.n}]


def main():
    print("页面数值断言 验证:\n")
    assert _num("待处理(12)") == "12" and _num("合计 ¥50.00") == "50.00" and _num("无") == "无"
    print("    ✓ 从'待处理(12)'/'合计 ¥50.00'抽出数字")

    reads = {".tab-pending": "待处理(3)", ".btn-sum": "合计 50"}
    ok, layer = check_values(reads, [
        {"selector": ".tab-pending", "db_scalar": "SELECT COUNT(*) c FROM x", "label": "待处理页签"},
        {"selector": ".btn-sum", "equals": "50"},
    ], db=FakeDB(3))
    assert ok, layer["rows"]
    print("    ✓ 页面 3 == 库 count 3;页面 50 == 字面量 50 → 通过")

    bad, _ = check_values({".tab": "待处理(3)"}, [{"selector": ".tab", "db_scalar": "x"}], db=FakeDB(5))
    assert not bad, "页面 3 vs 库 5 应失败"
    bad2, _ = check_values({".t": "5"}, [{"selector": ".t", "db_scalar": "x"}], db=None)
    assert not bad2, "无库连接应失败"
    print("    ✓ 页面≠库 / 无库 → 如实判失败")
    print("\n全部通过 ✅  —— 页面数值↔库标量/字面量 断言就位(解锁页签/按钮计算类)")


if __name__ == "__main__":
    main()
