"""就绪门禁 验证(离线、零业务):用中性接口/用例验跨源判定逻辑。
跑:python tests/test_readiness.py
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

from core.readiness import (  # noqa: E402
    Capabilities, compute_readiness, norm_endpoint, case_endpoints,
    write_readiness, load_readiness,
)


def _case(cid, name="", steps="", exp=""):
    return SimpleNamespace(case_id=cid, name=name, steps_text=steps, expected_text=exp,
                           preconditions="", notes="")


def main():
    print("就绪门禁 验证:\n")

    assert norm_endpoint("https://h.test/svc/api/order/close?x=1") == "/svc/api/order/close"
    assert norm_endpoint("/svc/api/item/detail/{id}") == "/svc/api/item/detail"
    print("    ✓ endpoint 规整(去域名/query/花括号)")

    caps = Capabilities(
        reachable={"/svc/api/order/create", "/svc/api/order/page"},
        catalog={"/svc/api/order/create", "/svc/api/order/page", "/svc/api/order/accept"},
        verified_cases={"C1"},
        rule_undefined={"C9"},
    )
    routes = {"by_case_id": {
        "C2": {"write": {"endpoint": {"method": "POST", "url": "/svc/api/order/create"}}},
        "C3": {"write": {"endpoint": {"method": "POST", "url": "/svc/api/order/accept"}}},
    }}
    cases = [
        _case("C1", "已建模"),
        _case("C2", "建单", "调用 /svc/api/order/create"),
        _case("C3", "受理", "调用 /svc/api/order/accept"),
        _case("C4", "未知动作", "点一个神秘按钮 /svc/api/order/mystery"),
        _case("C9", "规则未定"),
        _case("C5", "纯文本无接口", "看看页面"),
    ]
    items = {it.case_id: it for it in compute_readiness(cases, caps, routes)}

    assert items["C1"].ready and items["C1"].blocked_by == [], items["C1"]
    print("    ✓ C1 已有规格 → ready")
    assert items["C2"].ready, items["C2"]                       # create 可达
    print("    ✓ C2 接口可达 → ready")
    assert not items["C3"].ready and items["C3"].blocked_by == ["role"], items["C3"]  # accept 在 catalog 不在 reachable
    print("    ✓ C3 接口存在但够不到 → blocked_by role")
    assert not items["C4"].ready and items["C4"].blocked_by == ["action-body"], items["C4"]  # 系统没见过
    print("    ✓ C4 接口从未出现 → blocked_by action-body")
    assert not items["C9"].ready and items["C9"].blocked_by == ["rule"], items["C9"]
    print("    ✓ C9 规则未定义 → blocked_by rule")
    assert not items["C5"].ready and items["C5"].blocked_by == [], items["C5"]  # unknown 兜底
    print("    ✓ C5 无接口 → unknown(交兜底,不强判)")

    assert case_endpoints("C3", "", routes["by_case_id"]["C3"]) == {"/svc/api/order/accept"}
    print("    ✓ 路由优先取 endpoint")

    import tempfile
    d = tempfile.mkdtemp()
    fp = os.path.join(d, "readiness.yaml")
    write_readiness(fp, list(items.values()))
    back = load_readiness(fp)
    assert back["C3"]["blocked_by"] == ["role"] and back["C1"]["ready"] is True
    print("    ✓ 落盘/读回 readiness.yaml 一致")

    print("\n全部通过 ✅  —— 就绪与阻塞原因机器判定,零业务、离线可测")


if __name__ == "__main__":
    main()
