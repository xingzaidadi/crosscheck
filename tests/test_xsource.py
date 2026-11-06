"""
跨源不变式对账 验证(离线、零业务):派生视图列表的正确测法——完整性 + 一致性。

跑:python tests/test_xsource.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.xsource import reconcile_membership, align_api_rows  # noqa: E402


def main():
    print("跨源不变式对账 验证:\n")

    # 接口三行,库里都在,状态都一致 → PASS
    api = [{"code": "A1", "st": "TO_ACCEPT"}, {"code": "A2", "st": "ACCEPTING"}, {"code": "A3", "st": "TO_ACCEPT"}]
    db = [{"code": "A1", "st": "TO_ACCEPT"}, {"code": "A2", "st": "ACCEPTING"}, {"code": "A3", "st": "TO_ACCEPT"}, {"code": "Z9", "st": "DRAFT"}]
    r = reconcile_membership(api, db, key="code", consistency={"st": "st"})
    assert r["verdict"] == "PASS", r
    assert r["present"] == 3 and not r["missing"] and not r["mismatch"], r
    print(f"    ✓ 全在库+状态一致 → PASS({r['detail']});库里多出的 Z9 不影响(视图是子集)")

    # 接口冒出一行库里没有 → 完整性失败(派生视图捏造了不存在的单据)
    api2 = api + [{"code": "GHOST", "st": "TO_ACCEPT"}]
    r2 = reconcile_membership(api2, db, key="code", consistency={"st": "st"})
    assert r2["verdict"] == "FAIL" and r2["missing"] == ["GHOST"], r2
    print(f"    ✓ 接口多出库里没有的 GHOST → FAIL(完整性,missing={r2['missing']})")

    # 状态两边矛盾 → 一致性失败
    db3 = [{"code": "A1", "st": "CLOSED"}, {"code": "A2", "st": "ACCEPTING"}, {"code": "A3", "st": "TO_ACCEPT"}]
    r3 = reconcile_membership(api, db3, key="code", consistency={"st": "st"})
    assert r3["verdict"] == "FAIL" and r3["mismatch"] and r3["mismatch"][0]["key"] == "A1", r3
    print(f"    ✓ A1 接口 TO_ACCEPT 库里 CLOSED → FAIL(一致性,mismatch={r3['mismatch']})")

    # key 对齐:接口驼峰 → 库下划线
    aligned = align_api_rows([{"demandRequestCode": "A1"}], "demandRequestCode", "demand_request_code")
    assert aligned[0]["demand_request_code"] == "A1", aligned
    print("    ✓ align_api_rows 把接口 key 名对齐到库侧名")

    print("\n全部通过 ✅  —— 派生视图列表用跨源不变式验证(不做行数对账),受理台类用例就位")


if __name__ == "__main__":
    main()
