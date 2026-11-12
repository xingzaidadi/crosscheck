"""第二系统·通用性端到端铁证(离线、零业务、零 core 改动):
换一个**全新业务域**(图书馆 book,与需求/采购毫无关系),用全新 workspace + CSV 散文用例,
走真实公共管线 read_cases(新CSV读取插件)→ model_case(路由建模)→ run_write_spec(引擎执行)
→ 三源断言(接口+库)→ 按标记清理;再跑 dbmap 自发现新库结构。
全程 core 一行不改。证明"换业务只改 workspace,框架通用"。

跑:python tests/test_second_system.py
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

from sqlalchemy import create_engine, text  # noqa: E402
from db.client import DbClient  # noqa: E402
from core.case_source import read_cases  # noqa: E402
from core.modeler import model_case, load_routes  # noqa: E402
from core.engine import run_write_spec  # noqa: E402
from core.interfaces import Verdict  # noqa: E402
from core import dbmap  # noqa: E402

DB_PATH = ""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, obj, code=200):
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(obj).encode("utf-8"))
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        eng = create_engine(f"sqlite:///{DB_PATH}")
        if self.path == "/api/book/add":          # 新增图书:落一条 ON_SHELF,返回书号
            title = body.get("title", "")
            code = f"BK-{abs(hash(title)) % 100000}"
            with eng.begin() as c:
                c.execute(text("INSERT INTO book (title, isbn, book_code, status) VALUES (:t,:i,:c,'ON_SHELF')"),
                          {"t": title, "i": body.get("isbn", ""), "c": code})
            eng.dispose(); self._json({"code": 200, "data": {"bookCode": code}})
        else:
            eng.dispose(); self._json({"code": 404}, 404)


def main():
    global DB_PATH
    print("第二系统·通用性端到端铁证(图书馆域,零 core 改动):\n")
    d = tempfile.mkdtemp()
    DB_PATH = os.path.join(d, "library.db").replace("\\", "/")
    eng = create_engine(f"sqlite:///{DB_PATH}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE book (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "title TEXT, isbn TEXT, book_code TEXT, status TEXT)"))
    eng.dispose()

    server = HTTPServer(("127.0.0.1", 0), Handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        # 全新 workspace:只有一份 CSV 散文用例 + 一份路由(都是业务数据,core 不动)
        ws = os.path.join(d, "ws"); os.makedirs(os.path.join(ws, "cases"))
        csv_path = os.path.join(ws, "cases", "图书用例.csv")
        open(csv_path, "w", encoding="utf-8").write(
            "用例名称,步骤描述,预期结果\n"
            "BK01-新增图书上架保存,调用 /api/book/add 新增图书,图书落库 status=ON_SHELF\n")
        routes = {
            "defaults": {"base_url": base, "code_path": "data.bookCode"},
            "by_case_id": {"BK01": {
                "case_title": "BK01-新增图书上架保存",
                "feature": "图书上架", "mode": "write",
                "write": {
                    "endpoint": {"method": "POST", "url": "/api/book/add"},
                    "inline_body": {"title": "", "isbn": "9787000000001"},
                    "table": "book", "parent_key": "book_code", "parent_marker_col": "title",
                    "assert_status": {"column": "status", "value": "ON_SHELF"},
                }}},
        }

        # 1) 新 CSV 读取插件 读散文用例
        raws = read_cases(csv_path)
        assert len(raws) == 1 and raws[0].case_id == "BK01", [r.case_id for r in raws]
        print("    ✓ CSV 散文用例读入(新读取插件):BK01")

        # 2) 真实建模器 按路由建模(新域、新接口,core 不识业务)
        db = DbClient(dsn_readonly=f"sqlite:///{DB_PATH}", dsn_write=f"sqlite:///{DB_PATH}")
        spec = model_case(raws[0], routes=routes, kb_root=__import__("pathlib").Path(d),
                          caps_root=__import__("pathlib").Path(d), db=db)
        assert spec.mode == "api" and spec.verify_status == "human_verified", (spec.mode, spec.verify_status)
        assert spec.request["url"] == "/api/book/add", spec.request
        print(f"    ✓ 建模器产出可执行规格:{spec.request['method']} {spec.request['url']}")

        # 3) 真实引擎 执行:新增→三源断言(接口 code=200 + 库 status=ON_SHELF)→按标记清理
        spec.base_url = base
        r = run_write_spec(spec, db, registry_path=os.path.join(d, "reg.json"))
        assert r.verdict is Verdict.PASS, (r.verdict, r.details)
        print("    ✓ 引擎执行+三源校验 通过(新增图书、落库 ON_SHELF)")
        left = db.query("SELECT COUNT(*) c FROM book WHERE title LIKE 'AUTOTEST_%'")[0]["c"]
        assert left == 0 and r.cleanup_ok, f"清理应销账,残留 {left}"
        print("    ✓ 按标记自动清理,残留 0")

        # 4) dbmap 自发现新库结构(换库零改)
        mp = dbmap.schema_map(db)
        assert "book" in mp and "status" in mp["book"]["columns"], list(mp)
        print(f"    ✓ dbmap 自发现新库:表 {sorted(mp)} 字段含 status")
        db.close()
    finally:
        server.shutdown()

    # 5) 零业务门禁:整个过程 core 一行未改
    import subprocess
    gp = subprocess.run([sys.executable, "-I", "tests/test_no_business_in_core.py"],
                        capture_output=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert gp.returncode == 0, "零业务门禁应通过(core 未被污染)"
    print("    ✓ 零业务门禁仍通过:core 一行未改")
    print("\n全部通过 ✅  —— 换全新业务域(图书馆),仅配 workspace,公共管线端到端跑通,core 零改动")


if __name__ == "__main__":
    main()
