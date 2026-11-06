"""
防假通过 验证(mock 接口 + sqlite,离线):前置/审批失败绝不判 PASS。
对应改造方案"阶段0 可信底座:统一失败终态"。

跑:python tests/test_no_false_pass.py
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

DB = ""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, o, c=200):
        self.send_response(c); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(o).encode())
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/prep":
            self._j({"code": 500, "message": "prep boom"}, 500)       # 前置失败
        elif self.path == "/do":
            eng = create_engine(f"sqlite:///{DB}")
            with eng.begin() as c:
                c.execute(text("INSERT INTO t (name) VALUES (:n)"), {"n": b.get("name", "")})
            eng.dispose()
            self._j({"code": 200, "data": {"ok": True}})             # 主动作成功
        else:
            self._j({"code": 404}, 404)
    def do_GET(self):
        self._j({"code": -1, "message": "approve rejected"})         # 审批失败


def main():
    global DB
    import tempfile
    d = tempfile.mkdtemp(); DB = os.path.join(d, "a.db").replace("\\", "/")
    eng = create_engine(f"sqlite:///{DB}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)"))
    eng.dispose()
    srv = HTTPServer(("127.0.0.1", 0), H); base = f"http://127.0.0.1:{srv.server_address[1]}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print("防假通过 验证:\n")
    try:
        db = DbClient(dsn_readonly=f"sqlite:///{DB}", dsn_write=f"sqlite:///{DB}")
        # 1) 前置失败,但主动作+断言本会过 → 必须不是 PASS(应 ENV_ERROR)
        s1 = ExecSpec(case_id="FP1", title="前置失败不假通过", kind="write", mode="api",
                      verify_status="human_verified", base_url=base,
                      data_prep=[{"method": "POST", "url": "/prep", "body": {}}],
                      request={"method": "POST", "url": "/do", "body": {"name": "{{AUTOTEST_标记值}}"}},
                      assertions={"response": {"status": 200}, "db": [{"table": "t",
                                  "where": "name='{{AUTOTEST_标记值}}'", "row_count": 1}]},
                      cleanup=[{"table": "t", "column": "name"}], allowed_tables=["t"])
        r1 = run_write_spec(s1, db, registry_path=os.path.join(d, "r1.json"))
        assert r1.verdict is not Verdict.PASS, (r1.verdict, r1.details)
        assert r1.verdict is Verdict.ENV_ERROR, r1.verdict
        print(f"    ✓ 前置 data_prep 失败 → 判 {r1.verdict.value}(不假通过)")

        # 2) 审批失败 → 必须 FAIL(即便库断言通过)
        s2 = ExecSpec(case_id="FP2", title="审批失败不假通过", kind="write", mode="api",
                      verify_status="human_verified", base_url=base,
                      request={"method": "POST", "url": "/do", "body": {"name": "{{AUTOTEST_标记值}}"}},
                      approve={"method": "GET", "url": "/appr", "body": {}, "expect": {"body": {"code": 0}}},
                      assertions={"db": [{"table": "t", "where": "name='{{AUTOTEST_标记值}}'", "row_count": 1}]},
                      cleanup=[{"table": "t", "column": "name"}], allowed_tables=["t"])
        r2 = run_write_spec(s2, db, registry_path=os.path.join(d, "r2.json"))
        assert r2.verdict is Verdict.FAIL, (r2.verdict, r2.details)
        print(f"    ✓ 审批失败 → 判 {r2.verdict.value}(即便库断言本会过)")
        db.close()
    finally:
        srv.shutdown()
    print("\n全部通过 ✅  —— 前置/审批失败绝不假通过(阶段0 可信底座)")


if __name__ == "__main__":
    main()
