"""变异自检(离线、零业务):证"不造假"不是空话——植入错误断言,框架必须判 FAIL,不能蒙混 PASS。
同一本地系统:正确断言→PASS;错状态值→FAIL;错行数→FAIL;错响应字段→FAIL。
跑:python tests/test_mutation_guard.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402
from db.client import DbClient  # noqa: E402
from core.spec import ExecSpec  # noqa: E402
from core.engine import run_write_spec  # noqa: E402
from core.interfaces import Verdict  # noqa: E402

DB_PATH = ""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        eng = create_engine(f"sqlite:///{DB_PATH}")
        code = f"O-{abs(hash(body.get('title',''))) % 99999}"
        with eng.begin() as c:
            c.execute(text("INSERT INTO ord (title, code, status) VALUES (:t,:c,'DONE')"),
                      {"t": body.get("title", ""), "c": code})
        eng.dispose()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"code": 200, "data": {"orderCode": code}}).encode())


def _spec(base, asserts, resp=None):
    return ExecSpec(case_id="MUT", title="变异", kind="write", mode="api",
                    verify_status="human_verified", base_url=base,
                    request={"method": "POST", "url": "/add", "body": {"title": "{{marker}}"}},
                    assertions={"db": asserts, **({"response": resp} if resp else {})},
                    cleanup=[{"table": "ord", "column": "title"}], allowed_tables=["ord"])


def main():
    global DB_PATH
    print("变异自检(植入错断言必 FAIL):\n")
    d = tempfile.mkdtemp(); DB_PATH = os.path.join(d, "m.db").replace("\\", "/")
    eng = create_engine(f"sqlite:///{DB_PATH}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE ord (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, code TEXT, status TEXT)"))
    eng.dispose()
    server = HTTPServer(("127.0.0.1", 0), Handler); base = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        db = DbClient(dsn_readonly=f"sqlite:///{DB_PATH}", dsn_write=f"sqlite:///{DB_PATH}")
        reg = os.path.join(d, "reg.json")

        # 正确断言 → PASS
        r = run_write_spec(_spec(base, [{"table": "ord", "where": "title='{{AUTOTEST_标记值}}'",
                                         "row_count": 1, "fields": {"status": "DONE"}}]), db, registry_path=reg)
        assert r.verdict is Verdict.PASS, (r.verdict, r.details)
        print("    ✓ 正确断言 → PASS(落库 status=DONE)")

        # 变异①:错状态值 → 必 FAIL
        r = run_write_spec(_spec(base, [{"table": "ord", "where": "title='{{AUTOTEST_标记值}}'",
                                         "row_count": 1, "fields": {"status": "WRONG"}}]), db, registry_path=reg)
        assert r.verdict is Verdict.FAIL, f"错状态值应 FAIL,实得 {r.verdict}"
        print("    ✓ 错状态值 → FAIL(没蒙混)")

        # 变异②:错行数 → 必 FAIL
        r = run_write_spec(_spec(base, [{"table": "ord", "where": "title='{{AUTOTEST_标记值}}'",
                                         "row_count": 999}]), db, registry_path=reg)
        assert r.verdict is Verdict.FAIL, f"错行数应 FAIL,实得 {r.verdict}"
        print("    ✓ 错行数(预期999) → FAIL")

        # 变异③:错响应字段 → 必 FAIL
        r = run_write_spec(_spec(base, [{"table": "ord", "where": "title='{{AUTOTEST_标记值}}'", "row_count": 1}],
                                 resp={"body": {"code": 999}}), db, registry_path=reg)
        assert r.verdict is Verdict.FAIL, f"错响应字段应 FAIL,实得 {r.verdict}"
        print("    ✓ 错响应字段(预期 code=999) → FAIL")
        db.close()
    finally:
        server.shutdown()
    print("\n全部通过 ✅  —— 断言真正起门禁作用:该失败就失败,'不造假'非空话")


if __name__ == "__main__":
    main()
