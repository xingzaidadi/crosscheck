"""零人工路由直出(契约覆盖)判定 验证(离线、零业务)。

autobuild 维的分子之一是『零人工路由直出』:ready 用例的 ExecSpec 能从已摄取契约
直接建出、无需人工撰写路由。本测试锁死 core.readiness.contract_direct_cases 的诚实口径:
  - 用例接口被契约接口结构覆盖(精确/前缀,过 norm_endpoint 规整)才算零路由;
  - note 回捞接口、路由取接口两条来源都认;
  - ready 但无任何可核对接口痕迹 → 不计(不塞字样凑数);
  - 非 ready 一律不计;无契约 → 空集。

跑:python tests/test_contract_direct_routing.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.readiness import (  # noqa: E402
    contract_direct_cases, contract_endpoints, _endpoint_covered, norm_endpoint,
)


def main():
    print("零人工路由直出判定 验证:\n")

    # 契约接口可来自三种载体,统一规整为 path 集合
    as_list = [{"path": "/svc/api/order/detail/{id}", "http": "GET"},
               {"path": "/svc/api/order/page", "http": "POST"}]
    eps = contract_endpoints(as_list)
    assert eps == {"/svc/api/order/detail", "/svc/api/order/page"}, eps
    as_dict = {"site": "x", "source": "openapi", "endpoints": as_list}
    assert contract_endpoints(as_dict) == eps
    print("    ✓ 契约接口抽取(list / dict / 去{param})规整一致")

    # 接口覆盖:精确、前缀(字面量填参)、反向前缀
    assert _endpoint_covered("/svc/api/order/page", eps)
    assert _endpoint_covered("/svc/api/order/detail/REQ123", eps)  # 字面量填 {id}
    assert not _endpoint_covered("/svc/api/order/export", eps)     # 契约没有
    assert not _endpoint_covered("", eps)
    print("    ✓ 接口覆盖判定:精确/前缀(字面量填参)覆盖,未覆盖如实 False")

    readiness = {
        # ready + note 回捞接口命中契约 → 零路由
        "C1": {"ready": True, "blocked_by": [], "note": "接口可达: ['/svc/api/order/page']"},
        # ready + 路由接口命中契约(note 无接口)→ 零路由
        "C2": {"ready": True, "blocked_by": [], "note": "已有可跑规格"},
        # ready + 字面量填参接口命中契约 → 零路由
        "C3": {"ready": True, "blocked_by": [], "note": "接口可达: ['/svc/api/order/detail/REQ9']"},
        # ready 但无任何接口痕迹 → 不计(不凑数)
        "C4": {"ready": True, "blocked_by": [], "note": "已有可跑规格"},
        # ready 但接口不在契约(export)→ 不计
        "C5": {"ready": True, "blocked_by": [], "note": "接口可达: ['/svc/api/order/export']"},
        # 非 ready → 一律不计,即便接口命中
        "C6": {"ready": False, "blocked_by": ["role"], "note": "接口可达: ['/svc/api/order/page']"},
    }
    routes = {"by_case_id": {
        "C2": {"write": {"endpoint": {"method": "POST", "url": "/svc/api/order/page"}}},
        "C4": {"write": {}},  # 无 url → 无接口
    }}
    direct = contract_direct_cases(readiness, eps, routes)
    assert direct == {"C1", "C2", "C3"}, f"零路由集合应为 C1,C2,C3, got {sorted(direct)}"
    print("    ✓ 零路由集合 = {C1,C2,C3}(note/路由命中契约才算,无痕/未覆盖/非 ready 均排除)")

    # 无契约 → 空集(诚实不冒充)
    assert contract_direct_cases(readiness, set(), routes) == set()
    assert contract_direct_cases({}, eps, routes) == set()
    print("    ✓ 无契约 / 无 readiness → 空集(零路由=0,不冒充)")

    print("\n全部通过 ✅  —— 零路由直出由用例接口↔契约接口结构比对确定性判定,可复算、可单测")


if __name__ == "__main__":
    main()
