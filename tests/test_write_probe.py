"""
写接口自动发现 验证:从一堆抓包里挑出"写"调用,并产出写路由桩(endpoint+模板体)。
纯数据,离线 —— 证明 probe 录一次写操作就能自动得到 endpoint+提交体,免人工指定。

跑:python tests/test_write_probe.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.prober import Prober, Capture, write_stub_from_capture  # noqa: E402


def main():
    pr = Prober()
    pr.captures = [
        # 页面加载的读接口(GET)
        Capture(url="https://x/app/api/user/info", method="GET", resource_type="xhr",
                request_body=None, response_json={"code": 200, "data": {"name": "u"}}),
        # 检索(POST 但响应是列表/分页)—— 不该被当成写
        Capture(url="https://x/app/api/order/page", method="POST", resource_type="xhr",
                request_body={"pageNum": 1}, response_json={"code": 200, "data": {"list": [1, 2], "total": 2}}),
        # 真正的写:暂存(POST,带提交体,响应成功,无列表)
        Capture(url="https://x/app/api/order/draft?x=1", method="POST", resource_type="xhr",
                request_body={"title": "T", "qty": 1}, response_json={"code": 200, "success": True, "data": {"code": "R1"}}),
    ]

    print("写接口自动发现 验证:\n")
    w = pr.pick_write_call()
    assert w is not None and w.url.endswith("order/draft?x=1"), w
    print(f"    ✓ 从混合流量里挑出写调用: {w.method} {w.url}(排除了读接口和分页检索)")

    stub = write_stub_from_capture(w)
    assert stub["endpoint"] == {"method": "POST", "url": "/app/api/order/draft"}, stub["endpoint"]
    assert stub["template_body"] == {"title": "T", "qty": 1}, stub["template_body"]
    print(f"    ✓ 产出写路由桩: endpoint={stub['endpoint']} + 提交体模板(字段 {list(stub['template_body'])})")
    print("\n全部通过 ✅  —— probe 录一次写操作即得 endpoint+提交体模板,route 免手写接口")


if __name__ == "__main__":
    main()
