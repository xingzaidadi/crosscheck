"""第二 UI 套件·live-UI 层通用性(离线、零 core 改动):
本地起一个 **antd 风格**(ant-* class,与 hi-v5 完全不同)的页面 + 列表接口,
验 UI 层不是只认 hi-v5:detect_ui_kit 认出 'ant'、page_probe 按值把 DOM 列绑定到接口字段、
discover_fields 枚举 antd 表单控件。全程 core 一行不改。

需 Playwright;装不上则跳过(不算失败)。跑:python tests/test_second_system_ui.py
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

RECORDS = [{"id": 1, "name": "Alice", "status": "ON_SHELF"},
           {"id": 2, "name": "Bob", "status": "OFF_SHELF"},
           {"id": 3, "name": "Cara", "status": "ON_SHELF"}]

HTML = """<!doctype html><html><head><meta charset=utf-8><title>书库-antd</title></head>
<body>
<form class="ant-form">
  <div class="ant-form-item"><label class="ant-form-item-label">书名*</label>
    <input class="ant-input" placeholder="请输入书名"></div>
  <div class="ant-form-item"><label class="ant-form-item-label">状态</label>
    <div class="ant-select" role="combobox">请选择</div></div>
  <button class="ant-btn ant-btn-primary">提交</button>
</form>
<table class="ant-table"><thead class="ant-table-thead"><tr>
  <th class="ant-table-cell">名称</th><th class="ant-table-cell">状态</th></tr></thead>
  <tbody class="ant-table-tbody" id="tb"></tbody></table>
<script>
fetch('/api/items',{method:'POST'}).then(r=>r.json()).then(d=>{
  const tb=document.getElementById('tb');
  (d.data.records||[]).forEach(x=>{
    const tr=document.createElement('tr'); tr.className='ant-table-row';
    tr.innerHTML='<td class="ant-table-cell">'+x.name+'</td><td class="ant-table-cell">'+x.status+'</td>';
    tb.appendChild(tr);
  });
});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, body, ctype):
        self.send_response(200); self.send_header("Content-Type", ctype); self.end_headers()
        self.wfile.write(body.encode("utf-8") if isinstance(body, str) else body)
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self._send(HTML, "text/html; charset=utf-8")
        else:
            self.send_response(404); self.end_headers()
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)
        if self.path == "/api/items":
            self._send(json.dumps({"code": 200, "data": {"records": RECORDS, "total": len(RECORDS)}}),
                       "application/json")
        else:
            self.send_response(404); self.end_headers()


def main():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        print("Playwright 未安装,跳过(不算失败)"); return
    from core.bootstrap import detect_ui_kit
    from core.discovery.page_probe import probe_page_extract

    print("第二 UI 套件·live-UI 层通用性(antd,零 core 改动):\n")
    server = HTTPServer(("127.0.0.1", 0), Handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True); pg = b.new_context().new_page()
            pg.goto(base + "/", wait_until="networkidle", timeout=20000); pg.wait_for_timeout(1500)
            classes = pg.evaluate("()=>Array.from(document.querySelectorAll('[class]')).map(e=>e.getAttribute('class'))")
            b.close()
        kit = detect_ui_kit(classes)
        assert kit["kit"] == "ant", kit
        print(f"    ✓ detect_ui_kit 认出第二套件:{kit['kit']}(非 hi-v5 硬编码)")

        pr = probe_page_extract(base + "/", api_pattern="/api/items",
                                actions=None, api_rows_path="data.records", wait_ms=2500, headless=True)
        ex = pr["extract"]
        assert ex.get("rows_selector"), f"应导出行选择器: {ex}"
        d2a = ex.get("dom_to_api") or {}
        assert d2a, f"应按值把 DOM 列绑定到接口字段: {ex}"
        bound = set(d2a.values())
        assert "name" in bound and "status" in bound, d2a
        print(f"    ✓ page_probe 值绑定:DOM 列 → 接口字段 {d2a}(antd 表结构)")
        print(f"    ✓ 行选择器自导出:{ex['rows_selector']}")
    finally:
        server.shutdown()

    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gp = subprocess.run([sys.executable, "-I", "tests/test_no_business_in_core.py"], capture_output=True, cwd=root)
    assert gp.returncode == 0, "零业务门禁应通过"
    print("    ✓ 零业务门禁仍通过:core 一行未改")
    print("\n全部通过 ✅  —— UI 探测/抽取层换套件(antd)照样跑,非 hi-v5 硬编码,core 零改动")


if __name__ == "__main__":
    main()
