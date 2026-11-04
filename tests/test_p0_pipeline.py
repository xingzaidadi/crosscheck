"""
P0 整条命令链的端到端验证:probe →(模拟人审)→ reconcile。

本地起网页 + sqlite 库 + 一个临时 workspace,完整跑一遍 run_p0 的两个子命令,证明:
  - probe 能抓取、建模、产出草稿;
  - 人审后 reconcile 能连库对账并给出一致结论。

真实环境里只是把本地 URL 换成目标页面 URL、sqlite 换成测试库、workspace 换成你自己的目录而已。
全程写在临时 workspace 里,不碰真实业务数据。

跑:python tests/test_p0_pipeline.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.workspace import set_workspace, kb_dir, captures_dir, config_dir  # noqa: E402
import run_p0  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

REQUEST_BODY = {"name": "AUTOTEST", "status": ["draft", "active"], "page": 1, "pageSize": 20}
SEARCH_RESPONSE = {
    "data": {
        "list": [
            {"id": 1, "name": "AUTOTEST_甲", "category_id": 20, "status": "draft", "region": 1},
            {"id": 3, "name": "AUTOTEST_丙", "category_id": 10, "status": "active", "region": 1},
        ],
        "statusGroups": [
            {"status": "draft", "count": 2},    # 库里 draft 也应是 2
            {"status": "active", "count": 3},     # 库里 active 也应是 3
        ],
        "total": 2,
    }
}
PAGE_HTML = """<!doctype html><html><head><meta charset=utf-8></head><body>
<script>
fetch('/api/items/search',{method:'POST',headers:{'Content-Type':'application/json'},
 body: JSON.stringify(%s)}).then(r=>r.json());
</script></body></html>""" % json.dumps(REQUEST_BODY)

# 过 fixed_where(tenant=1,del=0)后: draft=2(id1,2), active=3(id3,4,7)
FIXTURE_ROWS = [
    (1, "AUTOTEST_甲", 20, "draft",  1, 1, 0),
    (2, "AUTOTEST_乙", 20, "draft",  1, 1, 0),
    (3, "AUTOTEST_丙", 10, "active", 1, 1, 0),
    (4, "AUTOTEST_丁", 20, "active", 2, 1, 0),
    (7, "AUTOTEST_庚", 20, "active", 1, 1, 0),
    (5, "AUTOTEST_戊", 20, "draft",  1, 1, 1),   # del=1 排除
    (6, "别人家的",     20, "draft",  1, 2, 0),   # 别租户 排除
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(PAGE_HTML.encode("utf-8"))
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(SEARCH_RESPONSE).encode("utf-8"))


def setup_sqlite(path: str):
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT,"
                       " category_id INT, status TEXT, region INT, tenant_id INT, delete_status INT)"))
        for r in FIXTURE_ROWS:
            c.execute(text("INSERT INTO items VALUES (:a,:b,:c,:d,:e,:f,:g)"),
                      dict(zip("abcdefg", r)))
    eng.dispose()


def main():
    tmp = tempfile.mkdtemp()
    ws = Path(tmp) / "ws"
    (ws / "config").mkdir(parents=True, exist_ok=True)
    set_workspace(ws)

    db_path = os.path.join(tmp, "p0.db").replace("\\", "/")
    setup_sqlite(db_path)

    # 临时 workspace 里的 db.yaml 指向 sqlite
    (config_dir() / "db.yaml").write_text(
        f"readonly:\n  dsn: \"sqlite:///{db_path}\"\nwrite:\n  dsn: \"\"\n", encoding="utf-8")

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    draft = kb_dir() / "query_mapping" / "列表检索.draft.json"
    approved = kb_dir() / "query_mapping" / "列表检索.json"
    try:
        print("P0 命令链端到端验证:\n")
        # ── 步骤 1: probe ──
        print("[1] probe —— 抓取 + 自动建模")
        run_p0.cmd_probe(Namespace(
            url=f"http://127.0.0.1:{port}/", feature="列表检索",
            url_pattern="/api/items/search", trigger=None, record=False,
            session=str(run_p0.auth_dir() / "test_p0.json"), wait=3000,
            db="app_test", table="items", pk="id", profile=None))
        assert draft.exists(), "草稿未生成"
        d = json.loads(draft.read_text(encoding="utf-8"))
        assert d["param_map"]["name"]["column"] == "name"
        assert d["param_map"]["status"]["op"] == "in"
        print("    ✓ 草稿参数→列匹配正确(DB 已连,自动匹配生效)\n")

        # ── 步骤 2: 模拟人审 ──
        print("[2] 模拟人审 —— 补 fixed_where、转 human_verified")
        d["fixed_where"] = "tenant_id = 1 AND delete_status = 0"
        d["verify_status"] = "human_verified"
        approved.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"    ✓ 另存为 {approved.name}\n")

        # ── 步骤 3: reconcile ──
        print("[3] reconcile —— 连库对账")
        try:
            run_p0.cmd_reconcile(Namespace(feature="列表检索", profile=None, db_readonly=None))
            code = 0
        except SystemExit as e:
            code = e.code
        assert code == 0, f"对账判为不一致(exit={code}),fixture 本应一致"
        print("\n    ✓ 对账一致,exit=0")
        print("\n全部通过 ✅  —— probe→人审→reconcile 整条命令链跑通")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
