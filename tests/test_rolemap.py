"""角色能力自发现 验证(离线、零业务):注入假 probe_fn + 假站点产物,验扫取/并集/差集。
跑:python tests/test_rolemap.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rolemap import (  # noqa: E402
    caps_from_catalog, build_rolemap, union_reachable, unique_per_role,
)


def main():
    print("角色能力自发现 验证:\n")

    # 1) schema 无关地从嵌套产物里扫 path
    cat = {"pages": [{"url": "https://h/app/list"}],
           "calls": [{"method": "POST", "path": "/svc/api/order/page?x=1"}],
           "misc": ["noise", "/svc/api/order/create", {"deep": ["/svc/api/item/detail/{id}"]}]}
    caps = caps_from_catalog(cat)
    assert "/svc/api/order/page" in caps and "/svc/api/order/create" in caps, caps
    assert "/svc/api/item/detail" in caps and "/app/list" in caps, caps
    print(f"    ✓ 递归扫 path(去 query/花括号): {sorted(caps)}")

    # 2) 注入假 probe_fn 模拟两个角色的可达集
    fake = {
        "demander": {"/svc/api/order/create", "/svc/api/order/page"},
        "acceptor": {"/svc/api/order/page", "/svc/api/order/accept", "/svc/api/order/reject"},
    }
    def probe(root_url, state, **kw):
        return fake[state]   # 用 state 当角色键取假数据
    rm = build_rolemap({"demander": "demander", "acceptor": "acceptor"},
                       root_url="https://h/app", probe_fn=probe)
    assert rm["demander"] == sorted(fake["demander"]), rm
    print("    ✓ 逐角色探能力集")

    uni = union_reachable(rm)
    assert uni == fake["demander"] | fake["acceptor"], uni
    print(f"    ✓ 并集(整套账号够得到的): {len(uni)} 个")

    uq = unique_per_role(rm)
    assert set(uq["acceptor"]) == {"/svc/api/order/accept", "/svc/api/order/reject"}, uq
    assert set(uq["demander"]) == {"/svc/api/order/create"}, uq
    print(f"    ✓ 差集:acceptor 独有 {uq['acceptor']}")

    # 3) 探失败角色记空集,不拖垮
    def flaky(root_url, state, **kw):
        if state == "bad":
            raise RuntimeError("boom")
        return {"/svc/api/x"}
    rm2 = build_rolemap({"ok": "ok", "bad": "bad"}, root_url="h", probe_fn=flaky)
    assert rm2["bad"] == [] and rm2["ok"] == ["/svc/api/x"], rm2
    print("    ✓ 单角色探失败 → 空集,不中断")

    print("\n全部通过 ✅  —— 角色能力机器自发现,零业务、离线可测")


if __name__ == "__main__":
    main()
