"""离线集成:走单对账打分接入执行引擎(本地 mock 接口 + sqlite,不碰真网)。
证明三件事(兼容真证明,非自比自):
  1. 正常写用例(带库断言)真跑 run_write_spec → 打分落地、db 腿被强制且满足、verdict 不受影响。
  2. 默认(非 strict):声明 act_via=ui 却经接口执行器(没走页面)→ **verdict 与普通跑完全一致(加法中立)**,
     只是分数低、审计记 ui_triggered=False。
  3. 开 strict 门禁:同一条"声明走单却没走"的用例 → verdict 被降级为 FAIL(门禁生效)。
跑:python tests/test_fidelity_integration.py
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
except Exception:  # noqa: BLE001
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402
from core.engine import run_write_spec  # noqa: E402
from core.spec import ExecSpec  # noqa: E402
from core.interfaces import Verdict  # noqa: E402
from db.client import DbClient  # noqa: E402

DB_PATH = ""
BASE = ""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # noqa: D401
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/api/items/create":
            eng = create_engine(f"sqlite:///{DB_PATH}")
            with eng.begin() as c:
                c.execute(text("INSERT INTO items (name, status, tenant_id) VALUES (:n,:s,1)"),
                          {"n": body.get("name", ""), "s": body.get("status", "draft")})
            eng.dispose()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"code": 200, "data": {"ok": True}}).encode())
        else:
            self.send_response(404); self.end_headers(); self.wfile.write(b"{}")


def _spec(case_id, act_via="auto") -> ExecSpec:
    return ExecSpec(
        case_id=case_id, title=f"{case_id}-新建条目", kind="write", mode="api", act_via=act_via,
        verify_status="human_verified", base_url=BASE,
        request={"method": "POST", "url": "/api/items/create",
                 "body": {"name": "{{AUTOTEST_标记值}}", "status": "draft"}},
        assertions={"response": {"status": 200, "body": {"code": 200}},
                    "db": [{"table": "items", "where": "name = '{{AUTOTEST_标记值}}' AND status = 'draft'",
                            "row_count": 1, "fields": {"status": "draft"}}]},
        cleanup=[{"table": "items", "column": "name"}], allowed_tables=["items"],
    )


def main():
    global DB_PATH, BASE
    d = tempfile.mkdtemp()
    DB_PATH = os.path.join(d, "app.db").replace("\\", "/")
    eng = create_engine(f"sqlite:///{DB_PATH}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, status TEXT, tenant_id INT)"))
    eng.dispose()
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    BASE = f"http://127.0.0.1:{srv.server_address[1]}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    reg = os.path.join(d, "registry.json")
    os.environ.pop("CROSSCHECK_STRICT_WALK", None)
    try:
        db = DbClient(dsn_readonly=f"sqlite:///{DB_PATH}", dsn_write=f"sqlite:///{DB_PATH}")

        # 1) 正常写用例(带库断言):打分落地、db 腿强制且满足、verdict=PASS
        r1 = run_write_spec(_spec("TCF01", act_via="auto"), db, registry_path=reg)
        assert r1.verdict is Verdict.PASS, (r1.verdict, r1.details)
        assert r1.fidelity and r1.fidelity.get("score") is not None, "应有打分"
        dmap = {x["name"]: x for x in r1.fidelity["dims"]}
        assert dmap["db_layer"]["applicable"] and dmap["db_layer"]["ok"], "db 腿应被强制且满足"
        assert dmap["api_layer"]["ok"], "接口腿应满足"
        print(f"    ✓ 正常写用例:verdict=PASS,打分 {r1.fidelity['score']}/{r1.fidelity['grade']},接口+库两腿满足")

        # 2) 默认非 strict:声明 act_via=ui 却经接口执行器(没走页面)→ verdict 与普通跑一致(中立)
        r2 = run_write_spec(_spec("TCF02", act_via="ui"), db, registry_path=reg)
        assert r2.verdict == r1.verdict, f"非 strict 下 verdict 必须与普通跑一致(加法中立),实际 {r2.verdict}"
        assert r2.ui_triggered is False and r2.audit.get("strict_gate") is False
        um = {x["name"]: x for x in r2.fidelity["dims"]}
        assert um["ui_driven"]["ok"] is False, "声明走单却没走,ui_driven 应判 False"
        assert r2.fidelity["score"] < r1.fidelity["score"], "没走页面分数应更低"
        print(f"    ✓ 声明走单却接口建单:verdict 不变({r2.verdict.value}),分数降到 {r2.fidelity['score']}/{r2.fidelity['grade']},审计记 ui_triggered=False")

        # 3) 开 strict 门禁:同样的用例 → verdict 被降级 FAIL
        os.environ["CROSSCHECK_STRICT_WALK"] = "1"
        try:
            r3 = run_write_spec(_spec("TCF03", act_via="ui"), db, registry_path=reg)
        finally:
            os.environ.pop("CROSSCHECK_STRICT_WALK", None)
        assert r3.verdict is Verdict.FAIL, f"strict 门禁下应降级 FAIL,实际 {r3.verdict}"
        assert r3.audit.get("strict_gate") is True
        assert any("门禁" in x for x in r3.details), r3.details
        print(f"    ✓ strict 门禁:同一'声明走单却没走'用例 → verdict 降级 {r3.verdict.value}(偷懒会红)")

        db.close()
    finally:
        srv.shutdown()
    print("\n全部通过 ✅  —— 打分默认加法中立(不改 verdict),strict 门禁按需让'走单却没走'翻红")


if __name__ == "__main__":
    main()
