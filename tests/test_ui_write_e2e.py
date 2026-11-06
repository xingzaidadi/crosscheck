"""
UI 写入端到端 验证(mock 同源页面+接口 + sqlite + Playwright,离线)。

证明 UI 回放/自愈已接进执行主链:run_ui_write_spec 开页面 → 语义回放填表 → 点提交
(页面 fetch 落 sqlite)→ 验库命中标记 → 按标记清理。全程无真实环境。

跑:python tests/test_ui_write_e2e.py(需本地 Playwright)
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

from sqlalchemy import create_engine, text  # noqa: E402

from core.spec import ExecSpec  # noqa: E402
from core.ui_check import run_ui_write_spec  # noqa: E402
from core.interfaces import Verdict  # noqa: E402
from db.client import DbClient  # noqa: E402

DB_PATH = ""

FORM = """<!doctype html><html><head><meta charset=utf-8></head><body>
<div class="form-item"><span class="label">标题</span><input id="t"></div>
<button id="save">保存</button>
<script>
document.getElementById('save').onclick=function(){
  fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({title:document.getElementById('t').value})});
};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(FORM.encode("utf-8"))

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        eng = create_engine(f"sqlite:///{DB_PATH}")
        with eng.begin() as c:
            c.execute(text("INSERT INTO orders (title) VALUES (:t)"), {"t": body.get("title", "")})
        eng.dispose()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"code": 200, "success": True}).encode("utf-8"))


def main():
    global DB_PATH
    import tempfile
    d = tempfile.mkdtemp()
    DB_PATH = os.path.join(d, "app.db").replace("\\", "/")
    eng = create_engine(f"sqlite:///{DB_PATH}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT)"))
    eng.dispose()

    server = HTTPServer(("127.0.0.1", 0), Handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("UI 写入端到端 验证:\n")
    db = DbClient(dsn_readonly=f"sqlite:///{DB_PATH}", dsn_write=f"sqlite:///{DB_PATH}")
    spec = ExecSpec(
        case_id="TCUIW01", title="UI写入-填表提交落库", kind="write", mode="ui",
        verify_status="human_verified", base_url=base,
        ui={"page_url": base + "/", "video": False, "wait_ms": 1500,
            "page_model": [
                {"action": "text", "label": "标题", "value": "{{marker}}"},
                {"action": "click", "text": "保存"},
            ]},
        assertions={"db": [{"table": "orders", "where": "title = '{{AUTOTEST_标记值}}'", "row_count": 1}]},
        cleanup=[{"table": "orders", "column": "title"}],
        allowed_tables=["orders"], verify_poll={"timeout_s": 5, "interval_s": 1},
    )
    rundir = os.path.join(d, "run")
    try:
        from pathlib import Path
        r = run_ui_write_spec(spec, db, Path(rundir))
        assert r.verdict is Verdict.PASS, (r.verdict, r.details)
        print("    ✓ 开页面→回放填表→点保存→页面落库→验库命中标记 (PASS)")
        assert r.cleanup_ok and db.query("SELECT COUNT(*) c FROM orders WHERE title LIKE 'AUTOTEST_%'")[0]["c"] == 0
        print("    ✓ 按标记清理,残留 0")
        names = [ly["name"] for ly in r.report["layers"]]
        assert "UI 操作回放(含自愈)" in names and any("库断言" in n for n in names), names
        print(f"    ✓ 富报告含层: {names}")
        db.close()
    finally:
        server.shutdown()
    print("\n全部通过 ✅  —— UI 回放/自愈已接进执行主链,UI 写入用例可端到端跑")


if __name__ == "__main__":
    main()
