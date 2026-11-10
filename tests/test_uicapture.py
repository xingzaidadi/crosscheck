"""离线单测:core.uicapture 采集管线。
本地起一个中性页(shop/items,无真网、无业务词),用 ui_capture 走两步,断言:
逐步截图 PNG/HTML 落地、接口往返被记录、evidence.json / index.html / 视频 生成。
跑:python tests/test_uicapture.py
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PAGE = b"""<!doctype html><meta charset='utf-8'><title>Shop</title>
<h1 id='t'>Item List</h1><button id='go'>Search</button><ul id='out'></ul>
<script>
async function load(){const r=await fetch('/api/items?q=x');const d=await r.json();
document.getElementById('out').innerHTML=d.list.map(x=>'<li>'+x+'</li>').join('');}
document.getElementById('go').onclick=load; load();
</script>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静音
        pass

    def do_GET(self):
        if self.path.startswith("/api/items"):
            body = json.dumps({"list": ["apple", "pear"], "total": 2}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers(); self.wfile.write(PAGE)


def main():
    from core.uicapture import ui_capture

    srv = HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    run_dir = ROOT / "tests" / "fixtures" / "_uicap_out"
    for f in run_dir.glob("*"):  # 清上一次
        try: f.unlink()
        except Exception: pass

    try:
        with ui_capture(None, run_dir, name="shop-search", headless=True,
                        record_video=True, trace=True, url_filter="/api/") as cap:
            cap.goto(base + "/", wait_ms=800)
            cap.shot("loaded")
            cap.page.click("#go")
            cap.page.wait_for_timeout(500)
            cap.shot("after_search")
            assert cap.page.locator("li").count() == 2, "页面应渲染 2 行"
    finally:
        srv.shutdown()

    # 断言:两步截图各有 PNG + HTML
    pngs = sorted(run_dir.glob("*.png")); htmls = sorted(run_dir.glob("*.html"))
    assert len(pngs) >= 2, f"应 ≥2 张截图,实得 {len(pngs)}"
    assert len(htmls) >= 2, f"应 ≥2 份 DOM 快照,实得 {len(htmls)}"

    # 清单
    man = json.loads((run_dir / "evidence.json").read_text(encoding="utf-8"))
    assert man["name"] == "shop-search"
    assert len(man["steps"]) == 2, f"应 2 步,实得 {len(man['steps'])}"
    assert (run_dir / "index.html").exists(), "应生成 index.html"

    # 路线:至少捕获一次 /api/items 往返,响应被解析
    calls = json.loads((run_dir / "calls.json").read_text(encoding="utf-8"))
    api = [c for c in calls if "/api/items" in c["url"]]
    assert api, f"应捕获 /api/items 往返,实得 {[c['url'] for c in calls]}"
    assert api[0]["status"] == 200 and api[0]["response_json"]["total"] == 2, "响应体应被记录解析"

    # 视频
    vids = list(run_dir.glob("*.webm"))
    assert man["video"] and vids, "应生成视频(webm)"

    print(f"✅ uicapture 全通过: 步骤={len(man['steps'])} 截图={len(pngs)} 路线={len(calls)} "
          f"视频={man['video']} trace={man['trace']}")


if __name__ == "__main__":
    main()
