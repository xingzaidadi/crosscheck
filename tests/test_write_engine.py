"""
写入类执行引擎 端到端验证(本地 mock 接口 + sqlite,不碰真实环境)。

本地起一个"应用":POST 建条目时把数据写进 sqlite(模拟服务端落库)。
引擎按 ExecSpec 跑:发请求(marker 代入)→ 校验响应+库 → diff 安全网 → 清理。证明:
  1. 正常:建条目 → 响应+库断言通过 → diff 只动 allowed 表 → 清理销账(PASS)。
  2. diff 安全网:动了未声明的表 → 判 FAIL(潜在副作用)。

跑:python tests/test_write_engine.py
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

from core.engine import run_write_spec  # noqa: E402
from core.spec import ExecSpec  # noqa: E402
from core.interfaces import Verdict  # noqa: E402
from db.client import DbClient  # noqa: E402

DB_PATH = ""   # 运行时填


def _insert(table: str, name: str, status: str):
    eng = create_engine(f"sqlite:///{DB_PATH}")
    with eng.begin() as c:
        c.execute(text(f"INSERT INTO {table} (name, status, tenant_id) VALUES (:n,:s,1)"),
                  {"n": name, "s": status})
    eng.dispose()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, obj, code=200):
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(obj).encode("utf-8"))

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/items/create":                 # 正常:只落 items
            _insert("items", body.get("name", ""), body.get("status", "draft"))
            self._json({"code": 200, "data": {"ok": True}})
        elif self.path == "/api/items/create_bad":            # 越界:还动了 audit(未声明)
            _insert("items", body.get("name", ""), body.get("status", "draft"))
            _insert("audit", body.get("name", ""), "log")
            self._json({"code": 200, "data": {"ok": True}})
        else:
            self._json({"code": 404}, 404)


def _setup_db():
    eng = create_engine(f"sqlite:///{DB_PATH}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, status TEXT, tenant_id INT)"))
        c.execute(text("CREATE TABLE audit (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, status TEXT, tenant_id INT)"))
    eng.dispose()


def _spec(case_id, url, allowed) -> ExecSpec:
    return ExecSpec(
        case_id=case_id, title=f"{case_id}-新建条目", kind="write", mode="api",
        verify_status="human_verified", base_url=BASE,
        request={"method": "POST", "url": url, "body": {"name": "{{AUTOTEST_标记值}}", "status": "draft"}},
        assertions={
            "response": {"status": 200, "body": {"code": 200}},
            "db": [{"table": "items",
                    "where": "name = '{{AUTOTEST_标记值}}' AND status = 'draft'",
                    "row_count": 1, "fields": {"status": "draft"}}],
        },
        cleanup=[{"table": "items", "column": "name"}, {"table": "audit", "column": "name"}],
        allowed_tables=allowed,
    )


BASE = ""


def main():
    global DB_PATH, BASE
    import tempfile
    d = tempfile.mkdtemp()
    DB_PATH = os.path.join(d, "app.db").replace("\\", "/")
    _setup_db()

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    BASE = f"http://127.0.0.1:{port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    reg = os.path.join(d, "registry.json")
    print("写入类执行引擎 验证:\n")
    try:
        db = DbClient(dsn_readonly=f"sqlite:///{DB_PATH}", dsn_write=f"sqlite:///{DB_PATH}")

        # 1) 正常:建条目 → 校验 → diff → 清理
        r1 = run_write_spec(_spec("TCW01", "/api/items/create", ["items"]), db, registry_path=reg)
        assert r1.verdict is Verdict.PASS, (r1.verdict, r1.details)
        assert r1.cleanup_ok, "清理应成功销账"
        left = db.query("SELECT COUNT(*) c FROM items WHERE name LIKE 'AUTOTEST_%'")[0]["c"]
        assert left == 0, f"清理后不应残留造数,实际 {left}"
        print("    ✓ 正常链路: 建条目→响应+库断言通过→diff 只动 items→清理销账 (PASS)")

        # 2) diff 安全网:动了未声明的 audit 表 → FAIL
        r2 = run_write_spec(_spec("TCW02", "/api/items/create_bad", ["items"]), db, registry_path=reg)
        assert r2.verdict is Verdict.FAIL, (r2.verdict, r2.details)
        assert any("未声明的表" in d and "audit" in d for d in r2.details), r2.details
        print("    ✓ diff 安全网: 动了未声明的 audit 表 → FAIL,并指出是 audit")

        db.close()
    finally:
        server.shutdown()
    print("\n全部通过 ✅  —— 写入类引擎(发请求→校验响应+库→diff 安全网→按 marker 清理)就位")


if __name__ == "__main__":
    main()
