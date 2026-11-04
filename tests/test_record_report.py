"""
录制 + 报告 流水线验证(headless,本地起页,不碰真实环境)。证明:
  - Prober 全程录视频(webm)、关键步骤截图、声明式 actions 驱动检索、抓到接口;
  - report.build_report 把视频/截图/接口/对账结论拼成一页 HTML。

真实跑只是把本地 URL 换成目标页、把动作换成"选筛选项、点查询"。

跑:python tests/test_record_report.py
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.prober import Prober  # noqa: E402
from core.report import build_report  # noqa: E402

RESP = {"data": {"list": [{"id": 1, "name": "条目甲"}, {"id": 2, "name": "条目乙"}], "total": 2}}
PAGE = """<!doctype html><html><head><meta charset=utf-8></head><body>
<h2>列表检索(mock)</h2>
<select id="tag"><option value="T1">T1</option><option value="T2">T2</option></select>
<button id="go">查询</button>
<script>
document.getElementById('go').onclick=function(){
  fetch('/api/items/search',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({tagCode:document.getElementById('tag').value,page:1,pageSize:20})}).then(r=>r.json());
};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(PAGE.encode("utf-8"))
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(RESP).encode("utf-8"))


def main():
    import tempfile
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    tmp = tempfile.mkdtemp()
    print("录制 + 报告 流水线验证:\n")
    try:
        # 声明式检索动作:选筛选项 → 点查询 → 截图(真实页就是换选择器)
        actions = [
            {"select": {"selector": "#tag", "value": "T1"}},
            {"screenshot": "selected_tag"},
            {"click": {"selector": "#go"}},
            {"wait_ms": {"ms": 600}},
            {"screenshot": "after_search"},
        ]
        prober = Prober(url_pattern="/api/items/search", session_file=None,
                        headless=True, video_dir=tmp, artifacts_dir=tmp)
        prober.probe(f"http://127.0.0.1:{port}/", wait_ms=800, actions=actions)

        assert prober.captures, "没抓到接口"
        picked = prober.pick_search_call()
        assert picked and picked.response_json["data"]["total"] == 2, "没认出检索接口"
        print(f"    ✓ 抓到接口 {picked.method} …/items/search,total=2")

        shots = prober.screenshots
        assert any(s["name"] == "selected_tag" for s in shots), "缺 selected_tag 截图"
        assert any(s["name"] == "after_search" for s in shots), "缺 after_search 截图"
        assert all(Path(s["path"]).exists() for s in shots), "截图文件不存在"
        print(f"    ✓ actions 驱动 + 截图 {len(shots)} 张(含 loaded/selected_tag/after_search)")

        assert prober.video_path and Path(prober.video_path).exists(), "视频未落盘"
        size = Path(prober.video_path).stat().st_size
        assert size > 0, "视频为空"
        print(f"    ✓ 全程视频已录制 webm,{size} 字节")

        report = build_report(
            Path(tmp) / "report.html",
            feature="列表检索", site="demo", page_url=f"http://127.0.0.1:{port}/",
            picked=picked.__dict__, reconcile_text="总数: 接口=2 == 库=2", consistent=True,
            screenshots=shots, video_path=prober.video_path, capture_count=len(prober.captures),
        )
        doc = report.read_text(encoding="utf-8")
        assert "对账一致" in doc and "items/search" in doc and "data:image/png;base64," in doc
        assert "<video" in doc
        print(f"    ✓ 报告生成,含对账结论 + 接口真值 + 内联截图 + 视频 → {report.name}")

        print("\n全部通过 ✅  —— 视频/截图/接口/报告 四件套就位,真实跑换 URL+选择器即可")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
