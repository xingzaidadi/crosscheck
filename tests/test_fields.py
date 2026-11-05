"""
前端探针 fields.py 验证(本地表单,headless)。证明通用地:
  - discover_fields 枚举出控件,判必填(label 带 * 或 required)、下拉可选值、控件类型;
  - read_validation_errors 读出校验报错文本。

跑:python tests/test_fields.py
"""
from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.discovery.fields import discover_fields, read_validation_errors  # noqa: E402

FORM = """<!doctype html><html><head><meta charset=utf-8></head><body>
<div class="form-item"><label class="label">名称*</label><input required placeholder="请输入名称"></div>
<div class="form-item"><label class="label">状态</label><select><option>草稿</option><option>启用</option></select></div>
<div class="form-item"><label class="label">预算金额*</label><input type="number"><span class="error">请输入预算金额</span></div>
<div class="form-item"><label class="label">备注</label><textarea placeholder="请输入备注"></textarea></div>
</body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(FORM.encode("utf-8"))


def main():
    srv = HTTPServer(("127.0.0.1", 0), H); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from playwright.sync_api import sync_playwright
    print("前端探针验证:\n")
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True); page = b.new_context().new_page()
        page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded"); page.wait_for_timeout(500)
        fields = {f["label"]: f for f in discover_fields(page)}
        srv.shutdown(); b.close()
    assert "名称" in fields and fields["名称"]["required"] is True, fields
    assert fields["名称"]["control"] == "text"
    print("    ✓ 枚举出『名称』: 必填 ✓, 类型 text")
    assert fields["状态"]["control"] == "select" and fields["状态"]["options"] == ["草稿", "启用"], fields["状态"]
    print("    ✓ 枚举出『状态』: select, 可选值", fields["状态"]["options"])
    assert fields["预算金额"]["required"] is True and fields["预算金额"]["control"] == "number"
    print("    ✓ 枚举出『预算金额』: 必填 ✓, 类型 number")
    assert fields["备注"]["required"] is False
    print("    ✓ 『备注』非必填")
    # 校验报错(本例页面已内嵌一个 .error)
    srv2 = HTTPServer(("127.0.0.1", 0), H); port2 = srv2.server_address[1]
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True); page = b.new_context().new_page()
        page.goto(f"http://127.0.0.1:{port2}/", wait_until="domcontentloaded"); page.wait_for_timeout(300)
        errs = read_validation_errors(page)
        srv2.shutdown(); b.close()
    assert any("预算金额" in e for e in errs), errs
    print("    ✓ 读出校验报错:", errs)
    print("\n全部通过 ✅  —— 通用前端探针(控件/必填/可选值/报错)就位")


if __name__ == "__main__":
    main()
