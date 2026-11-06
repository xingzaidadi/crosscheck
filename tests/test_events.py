"""
异步/事件校验 验证(mock HTTP sink + sqlite,离线)。

证明通用"等待+轮询+计数"原语两源都能用、且真的"等":
  - http 源:外部通知接口在 2s 后才出现带标记的事件 → within_s=6 能等到(PASS);within_s=1 等不到(FAIL)。
  - db 源 :事件表里有带标记的行 → 命中(PASS);没有 → 不命中(FAIL)。

跑:python tests/test_events.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402

from core.events import check_events  # noqa: E402
from db.client import DbClient  # noqa: E402

MARK = "AUTOTEST_EV_1"
APPEAR_AT = 0.0   # 事件在此刻后才"落地"(模拟异步链路延迟)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        landed = time.time() >= APPEAR_AT
        data = {"list": ([{"requestTitle": MARK}] if landed else [])}
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"code": 200, "data": data}).encode("utf-8"))


def main():
    global APPEAR_AT
    server = HTTPServer(("127.0.0.1", 0), Handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("异步/事件校验 验证:\n")
    try:
        # 1) http 源:事件 2s 后才落地,within_s=6 应等到
        APPEAR_AT = time.time() + 2
        a_http = {"source": "http", "url": "/outbox", "list_path": "data.list",
                  "match_field": "requestTitle", "min_count": 1, "within_s": 6, "interval_s": 1,
                  "name": "通知网关"}
        ok, _, layers = check_events([a_http], marker=MARK, base_url=base)
        assert ok, layers
        print("    ✓ http 源: 2s 后落地的通知,6s 内轮询等到 → PASS")

        # 2) 反证:within_s=1 太短,等不到 → FAIL
        APPEAR_AT = time.time() + 3
        a_short = dict(a_http); a_short["within_s"] = 1
        ok2, _, _ = check_events([a_short], marker=MARK, base_url=base)
        assert not ok2, "时限太短不该通过"
        print("    ✓ http 源: 时限太短(1s)等不到 → FAIL(证明确实在等、非空过)")

        # 3) db 源:事件表有带标记的行 → 命中
        d = __import__("tempfile").mkdtemp()
        dbp = os.path.join(d, "ev.db").replace("\\", "/")
        eng = create_engine(f"sqlite:///{dbp}")
        with eng.begin() as c:
            c.execute(text("CREATE TABLE events (id INTEGER PRIMARY KEY, name TEXT)"))
            c.execute(text("INSERT INTO events (name) VALUES (:n)"), {"n": MARK})
        eng.dispose()
        db = DbClient(dsn_readonly=f"sqlite:///{dbp}")
        a_db = {"source": "db", "table": "events",
                "where": "name = '{{AUTOTEST_标记值}}'", "min_count": 1, "within_s": 2, "name": "事件表"}
        ok3, _, _ = check_events([a_db], marker=MARK, db=db)
        assert ok3, "事件表有标记行应命中"
        print("    ✓ db 源: 事件表里带标记的行 → 命中 PASS")
        a_db2 = dict(a_db); a_db2["where"] = "name = 'NOPE'"
        ok4, _, _ = check_events([a_db2], marker=MARK, db=db)
        assert not ok4, "无匹配行不该通过"
        print("    ✓ db 源: 无匹配 → FAIL")
        db.close()
    finally:
        server.shutdown()
    print("\n全部通过 ✅  —— 通用异步/事件校验(db + 外部 sink 两源,带等待)就位")


if __name__ == "__main__":
    main()
