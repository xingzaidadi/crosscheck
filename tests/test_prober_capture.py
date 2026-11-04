"""
探针抓取 → 自动建模 的端到端验证(本地 fixture,不碰真实环境)。

起一个本地网页:加载时自己发一个检索 XHR(POST 请求体 + JSON 返回)。
探针去打开这个页面、拦截到那次调用,证明:
  1. 请求体和返回 JSON 是工具自己抓的(人只给了 URL)。
  2. pick_search_call 能从流量里认出检索接口。
  3. build_mapping_draft 能据此 + 库列,自动推出映射草稿。

跑:python tests/test_prober_capture.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.prober import Prober  # noqa: E402
from core.mapping_builder import build_mapping_draft  # noqa: E402


SEARCH_RESPONSE = {
    "data": {
        "list": [
            {"id": 1, "name": "AUTOTEST_甲", "category_id": 20, "status": "active", "region": 1},
            {"id": 2, "name": "AUTOTEST_乙", "category_id": 20, "status": "active", "region": 1},
        ],
        "statusGroups": [
            {"status": "active", "count": 2},
            {"status": "draft", "count": 5},
        ],
        "total": 2,
    }
}

PAGE_HTML = """<!doctype html><html><head><meta charset=utf-8></head>
<body><h1>items search fixture</h1>
<script>
// 页面一加载就发一次检索请求,模拟真实 SPA 的检索接口
fetch('/api/items/search', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({name: 'AUTOTEST', categoryId: 20, status: ['active'], page: 1, pageSize: 20})
}).then(r => r.json()).then(j => { window.__done = true; });
</script></body></html>"""

DB_COLUMNS = ["id", "name", "category_id", "status", "region", "tenant_id", "delete_status"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静音
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE_HTML.encode("utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        _ = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(SEARCH_RESPONSE).encode("utf-8"))


def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print("探针抓取 → 自动建模 验证:")
    try:
        prober = Prober(url_pattern="/api/items/search", headless=True)
        prober.probe(f"http://127.0.0.1:{port}/", wait_ms=3000)

        assert prober.captures, "没抓到任何接口调用"
        print(f"  ✓ 抓到 {len(prober.captures)} 次接口调用(请求体+返回由工具自获取)")

        call = prober.pick_search_call()
        assert call is not None, "没认出检索接口"
        assert call.method == "POST"
        assert call.request_body and call.request_body.get("name") == "AUTOTEST"
        assert call.response_json["data"]["total"] == 2
        print(f"  ✓ pick_search_call 认出检索接口: {call.method} …{call.url.split('/')[-1]}")
        print(f"    抓到的请求体: {call.request_body}")

        draft = build_mapping_draft(call, db_name="app_test",
                                    table="items", pk="id", columns=DB_COLUMNS)
        pm = draft["param_map"]
        # name→name(like)、categoryId→category_id(eq, camel→snake)、status→status(in)
        assert pm["name"]["column"] == "name" and pm["name"]["op"] == "like"
        assert pm["categoryId"]["column"] == "category_id"
        assert pm["status"]["column"] == "status" and pm["status"]["op"] == "in"
        # 分页参数被排除
        assert "page" not in pm and "pageSize" not in pm
        # 分组自动识别
        assert draft["group_by"]["response_path"] == "data.statusGroups"
        assert draft["group_by"]["sql_group_column"] == "status"
        # 字段抽样列 = 返回行字段 ∩ 库列
        assert set(draft["field_sample_check"]["compare_fields"]) == {
            "id", "name", "category_id", "status", "region"}
        print("  ✓ build_mapping_draft 自动推出映射: 参数→列 / 分组 / 抽样字段全部命中")
        print("    ↓ 生成的映射草稿(节选):")
        slim = {k: draft[k] for k in ("param_map", "group_by", "field_sample_check")}
        for line in json.dumps(slim, ensure_ascii=False, indent=2).splitlines():
            print("      " + line)
    finally:
        server.shutdown()
    print("\n全部通过 ✅  —— 人只给了一个 URL,请求体/返回/映射草稿都是工具产出的")


if __name__ == "__main__":
    main()
