"""
前置造数 + 返回值串联 验证(sqlite + 本地 mock 接口,离线)。

证明状态机/编辑类用例的前提能力:
  data_prep 先造一张草稿(DRAFT)→ capture 抓回它的单号 → 主动作用 {{draftCode}} 引用它
  → 服务端把它流转成 SUBMITTED → 断言用 {{draftCode}} 命中并校验状态 → 按标记清理。
全程不碰真实环境。

跑:python tests/test_data_prep.py
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

DB_PATH = ""
SUBMITTED_WITH = {}   # 记录 submit 实际收到的 orderCode,证明主动作确实引用了抓到的单号


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, obj, code=200):
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(obj).encode("utf-8"))

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        eng = create_engine(f"sqlite:///{DB_PATH}")
        if self.path == "/draft":                 # 造草稿:落一张 DRAFT 单,返回系统单号
            name = body.get("name", "")
            code = f"D-{abs(hash(name)) % 100000}"
            with eng.begin() as c:
                c.execute(text("INSERT INTO orders (name, code, status) VALUES (:n,:c,'DRAFT')"),
                          {"n": name, "c": code})
            eng.dispose()
            self._json({"code": 200, "data": {"orderCode": code}})
        elif self.path == "/submit":              # 提交:按单号把该单流转 SUBMITTED
            oc = body.get("orderCode", "")
            SUBMITTED_WITH["orderCode"] = oc
            with eng.begin() as c:
                c.execute(text("UPDATE orders SET status='SUBMITTED' WHERE code=:c"), {"c": oc})
            eng.dispose()
            self._json({"code": 200, "data": {"ok": True}})
        else:
            eng.dispose(); self._json({"code": 404}, 404)


def main():
    global DB_PATH
    import tempfile
    d = tempfile.mkdtemp()
    DB_PATH = os.path.join(d, "app.db").replace("\\", "/")
    eng = create_engine(f"sqlite:///{DB_PATH}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, code TEXT, status TEXT)"))
    eng.dispose()

    server = HTTPServer(("127.0.0.1", 0), Handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("前置造数 + 返回值串联 验证:\n")
    try:
        db = DbClient(dsn_readonly=f"sqlite:///{DB_PATH}", dsn_write=f"sqlite:///{DB_PATH}")
        spec = ExecSpec(
            case_id="TCDP01", title="状态机-草稿提交流转", kind="write", mode="api",
            verify_status="human_verified", base_url=base,
            data_prep=[{"method": "POST", "url": "/draft",
                        "body": {"name": "{{AUTOTEST_标记值}}"},
                        "capture": {"draftCode": "data.orderCode"}}],
            request={"method": "POST", "url": "/submit", "body": {"orderCode": "{{draftCode}}"}},
            assertions={"db": [{"table": "orders",
                                "where": "code = '{{draftCode}}' AND status = 'SUBMITTED'",
                                "row_count": 1, "fields": {"status": "SUBMITTED"}}]},
            cleanup=[{"table": "orders", "column": "name"}],
            allowed_tables=["orders"],
        )
        r = run_write_spec(spec, db, registry_path=os.path.join(d, "reg.json"))
        assert r.verdict is Verdict.PASS, (r.verdict, r.details)
        print("    ✓ 造草稿→抓单号→主动作用 {{draftCode}} 引用→流转 SUBMITTED→断言命中 (PASS)")
        assert SUBMITTED_WITH.get("orderCode", "").startswith("D-"), SUBMITTED_WITH
        print(f"    ✓ 主动作确实带着抓到的单号提交: orderCode={SUBMITTED_WITH['orderCode']}")
        left = db.query("SELECT COUNT(*) c FROM orders WHERE name LIKE 'AUTOTEST_%'")[0]["c"]
        assert left == 0, f"清理后不应残留,实际 {left}"
        assert r.cleanup_ok, "应销账"
        print("    ✓ 按标记清理销账,残留 0")
        db.close()
    finally:
        server.shutdown()
    print("\n全部通过 ✅  —— 前置造数→抓返回值→主动作/断言引用 的状态机前提能力就位")


if __name__ == "__main__":
    main()
