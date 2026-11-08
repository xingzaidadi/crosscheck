"""动作报文自发现 验证(离线、零业务):注入假 prober 产一次写调用,验抓取/规整/转路由/落盘/端点集。
跑:python tests/test_actionmap.py
"""
from __future__ import annotations

import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workspace import set_workspace  # noqa: E402
from core.prober import Capture  # noqa: E402
from core.actionmap import (  # noqa: E402
    capture_action, normalize_stub, stub_to_route, save_action_stub,
    endpoints_from_stubs, build_actionmap,
)


class _FakeProber:
    def __init__(self, cap):
        self._cap = cap
    def pick_write_call(self):
        return self._cap


def main():
    print("动作报文自发现 验证:\n")
    set_workspace(tempfile.mkdtemp())

    cap = Capture(url="https://h/svc/api/order/close?t=1", method="POST", resource_type="xhr",
                  request_body={"id": 99, "orderCode": "X1", "closeReason": "x", "title": "t"},
                  response_json={"code": 0})

    # 1) capture_action:注入假 prober → 得动作桩
    def probe_fn(page_url, **kw):
        assert kw.get("session_file") == "/s.json"
        return _FakeProber(cap)
    stub = capture_action("https://h/app", probe_fn=probe_fn, session_file="/s.json",
                          actions=[{"click": {"selector": "text=关闭"}}])
    assert stub["endpoint"] == {"method": "POST", "url": "/svc/api/order/close"}, stub
    assert stub["template_body"]["orderCode"] == "X1", stub
    print(f"    ✓ 抓到动作桩: {stub['endpoint']}")

    # 抓不到写调用 → None
    assert capture_action("h", probe_fn=lambda u, **k: _FakeProber(None)) is None
    print("    ✓ 未触发写调用 → None")

    # 2) normalize_stub:去自增 id、标记字段注占位
    nz = normalize_stub(stub, marker_fields=["title"], drop_fields=["id"])
    assert "id" not in nz["template_body"] and nz["template_body"]["title"] == "{{marker}}", nz
    print("    ✓ 规整:去 id、title 注 {{marker}}")

    # 3) stub_to_route:桩 → 可执行 write 路由片段
    r = stub_to_route(stub, marker_fields=["title"], table="t_order",
                      parent_key="order_code", parent_marker_col="title",
                      assert_status={"column": "status", "value": "CLOSED"})
    assert r["mode"] == "write" and r["write"]["endpoint"]["url"] == "/svc/api/order/close"
    assert r["write"]["table"] == "t_order" and r["write"]["assert_status"]["value"] == "CLOSED"
    print("    ✓ 转 case_routes write 片段(endpoint+表+断言)")

    rj = stub_to_route(stub, expect_rejected=True)
    assert rj["write"]["response"] == {"rejected": True} and rj["write"]["assert_row_count"] == 0
    print("    ✓ 负向动作 → rejected + row_count 0")

    # 4) 落盘 + 端点集(喂 readiness.reachable)
    save_action_stub("demo", "order_close", stub)
    eps = endpoints_from_stubs("demo")
    assert eps == {"/svc/api/order/close"}, eps
    print(f"    ✓ 落盘 + 端点集: {eps}")

    # 5) build_actionmap 批量 + 容错
    res = build_actionmap("demo", [
        {"key": "a1", "page_url": "h", "session_file": "/s.json"},
        {"key": "a2", "page_url": "h"},   # 抓不到 → ok False
    ], probe_fn=lambda u, **k: _FakeProber(cap if k.get("session_file") else None))
    assert res["a1"]["ok"] and not res["a2"]["ok"], res
    print("    ✓ 批量录制 + 单条容错")

    print("\n全部通过 ✅  —— 动作报文机器录制成桩、转可执行、喂就绪门禁,零业务离线可测")


if __name__ == "__main__":
    main()
