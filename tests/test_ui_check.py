"""
UI 渲染校验(库↔接口↔页面 三层里的"页面↔接口"层)端到端验证。
本地起一个页面:加载后调 mock 接口、把返回渲染成表格。引擎渲染页面→抓接口→抽 DOM→比。证明:
  1. 正常页:页面显示的行 == 接口返回 → PASS(真比了行,非空跳过);
  2. 坏页:渲染出错值 → 抓出"第N行 字段 页面 vs 接口"差异 → FAIL。

跑:python tests/test_ui_check.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workspace import set_workspace  # noqa: E402
from core.spec import ExecSpec  # noqa: E402
from core.ui_check import run_ui_spec  # noqa: E402
from core.interfaces import Verdict  # noqa: E402

RECORDS = [{"name": "条目甲", "status": "active"}, {"name": "条目乙", "status": "draft"}]
RESP = {"code": 200, "data": {"records": RECORDS, "total": 2}}
DETAIL_RESP = {"code": 200, "data": {"itemName": "甲物", "itemStatus": "启用"}}
DETAIL = """<!doctype html><html><head><meta charset=utf-8></head><body>
<script>
fetch('/api/items/detail').then(r=>r.json()).then(j=>{
  const d=j.data;
  document.body.innerHTML += '<span class=lab>名称</span><span class=val>'+d.itemName+'</span>'
                           + '<span class=lab>状态</span><span class=val>'+d.itemStatus+'</span>';
});
</script></body></html>"""

def _page(name_expr):
    return ("""<!doctype html><html><head><meta charset=utf-8></head><body>
<table id=t><tbody></tbody></table>
<script>
fetch('/api/items/search',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})
 .then(r=>r.json()).then(j=>{
   const tb=document.querySelector('#t tbody');
   j.data.records.forEach(x=>{
     const tr=document.createElement('tr');
     tr.innerHTML='<td class=name>'+(%s)+'</td><td class=status>'+x.status+'</td>';
     tb.appendChild(tr);
   });
 });
</script></body></html>""" % name_expr)

GOOD = _page("x.name")          # 正常:显示接口返回的 name
BAD = _page("'错误值'")          # 故障:名字渲染成固定错值


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/api/items/detail"):
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps(DETAIL_RESP).encode("utf-8")); return
        html = DETAIL if self.path.startswith("/detail") else (GOOD if self.path.startswith("/good") else BAD)
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(html.encode("utf-8"))
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(RESP).encode("utf-8"))


def _spec(cid, path, base):
    return ExecSpec(case_id=cid, title=cid, kind="query", mode="ui", verify_status="human_verified",
                    base_url=base, session="",
                    ui={"page_url": base + path, "url_pattern": "/api/items/search", "wait_ms": 1800,
                        "extract": {"rows_selector": "#t tbody tr",
                                    "columns": {"name": "td.name", "status": "td.status"}},
                        "dom_to_api": {"name": "name", "status": "status"},
                        "api_rows_path": "data.records"})


def _spec_fields(cid, path, base):
    return ExecSpec(case_id=cid, title=cid, kind="query", mode="ui", verify_status="human_verified",
                    base_url=base, session="",
                    ui={"page_url": base + path, "url_pattern": "/api/items/detail", "wait_ms": 1800,
                        "extract": {"fields": {"label": ".lab", "value": ".val"}},
                        "dom_to_api": {"名称": "itemName", "状态": "itemStatus"},
                        "api_rows_path": "data"})


def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("UI 渲染校验验证:\n")
    with tempfile.TemporaryDirectory() as d:
        set_workspace(d)
        try:
            r1 = run_ui_spec(_spec("UI01", "/good", base), db=None)
            assert r1.verdict is Verdict.PASS, (r1.verdict, r1.details)
            assert any("渲染校验" in x and "一致" in x for x in r1.details), r1.details
            print("    ✓ 正常页: 页面显示 2 行 == 接口返回 → PASS")
            assert r1.video and os.path.exists(r1.video), f"无头也应录到视频: {r1.video!r}"
            print("    ✓ 无头录到操作视频:", os.path.basename(r1.video))

            r2 = run_ui_spec(_spec("UI02", "/bad", base), db=None)
            assert r2.verdict is Verdict.FAIL, (r2.verdict, r2.details)
            assert any("页面=" in x and "接口=" in x for x in r2.details), r2.details
            print("    ✓ 坏页: 渲染错值 → 抓出显示差异 → FAIL")
            print("      样例:", next(x for x in r2.details if "页面=" in x))

            # 3) 详情 fields 模式:标签→值 zip 配对,页面显示 == 接口
            r3 = run_ui_spec(_spec_fields("UI03", "/detail", base), db=None)
            assert r3.verdict is Verdict.PASS, (r3.verdict, r3.details)
            print("    ✓ 详情(fields 模式): 标签→值 == 接口 → PASS")

            # 4) 空值防护:页面空、接口非空 必须判不一致(防假性通过回归)
            from core.ui_verifier import verify_display
            rg = verify_display([{"名称": ""}], {"data": {"itemName": "甲物"}},
                                {"dom_to_api": {"名称": "itemName"}, "api_rows_path": "data"})
            assert not rg.consistent, "页面空值不该判一致(假性通过)"
            print("    ✓ 空值防护: 页面空 vs 接口非空 → 判不一致")
        finally:
            server.shutdown()
    print("\n全部通过 ✅  —— 库↔接口↔页面 的『页面↔接口』渲染校验层就位")


if __name__ == "__main__":
    main()
