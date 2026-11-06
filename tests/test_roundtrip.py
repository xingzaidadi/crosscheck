"""
全字段对账 验证(离线、零业务):提交体 ↔ 持久化记录 逐字段比。

跑:python tests/test_roundtrip.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.roundtrip import compare, _eq  # noqa: E402


def main():
    print("全字段对账 验证:\n")
    assert _eq("2", "2.0000") and _eq(10, "10.00") and not _eq("a", "b")
    print("    ✓ 数字宽松比:2==2.0000、10==10.00;文本不等照旧")

    submitted = {"title": "X", "qty": "2", "remark": "hi",
                 "itemList": [{"price": "10", "note": "a"}]}
    persisted = {"title": "X", "qty": "2.0000", "remark": "",   # remark 被漏填!
                 "itemList": [{"price": "10.00", "note": "a"}], "id": 99}

    ok, mism, layer = compare(submitted, persisted, ignore=["id"], item_key="itemList")
    assert not ok and mism == [("remark", "hi", "")], mism
    print(f"    ✓ 抓出字段级漏填:{mism}(qty 2↔2.0000、price 10↔10.00 宽松判等,不误报)")

    ok2, _, _ = compare(submitted, persisted, ignore=["id", "remark"], item_key="itemList")
    assert ok2, "remark 列入 ignore 后应全一致"
    print("    ✓ ignore 掉服务端合法改写的字段后,全一致")

    # 子项字段被改写
    s2 = {"itemList": [{"price": "10", "qty": "3"}]}
    p2 = {"itemList": [{"price": "10", "qty": "1"}]}   # qty 被改成 1!
    ok3, mism3, _ = compare(s2, p2, item_key="itemList")
    assert not ok3 and mism3 == [("itemList[0].qty", "3", "1")], mism3
    print(f"    ✓ 抓出子项字段被改写:{mism3}")
    print("\n全部通过 ✅  —— 全字段对账(提交↔落库 逐字段)就位,字段级 bug 自动现形")


if __name__ == "__main__":
    main()
