import csv
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.ui_test import run


class _PageHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = ("<html><body><button>详情</button>"
                "<div id='order' hidden>订单编号</div>"
                "<script>document.querySelector('button').onclick=()=>"
                "document.querySelector('#order').hidden=false</script></body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


class _TabsHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = ("<html><body><div role='tablist'>"
                "<button role='tab'>待处理</button><button role='tab'>执行中</button>"
                "<button role='tab'>全部</button><button role='tab'>整单查询</button>"
                "<button role='tab'>明细查询</button></div><div>列表已加载</div></body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def test_ui_test_runs_real_browser_and_writes_evidence(tmp_path: Path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cases = tmp_path / "cases.csv"
    with cases.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["name", "steps_text", "expected_text"])
        writer.writeheader()
        writer.writerow({"name": "TC1-详情", "steps_text": "点击\"详情\"",
                         "expected_text": "显示\"订单编号\""})
    try:
        result = run(type("Args", (), {
            "cases": str(cases), "url": f"http://127.0.0.1:{server.server_port}/",
            "workspace": str(tmp_path / "workspace"), "session": None, "run_id": "e2e",
            "only": None, "allow_write": False, "headed": False, "timeout_ms": 10000,
            "wait_ms": 50,
        })())
    finally:
        server.shutdown()
        thread.join(timeout=2)
    assert result["counts"] == {"PASS": 1}, repr(result)
    case = result["cases"][0]
    assert case["execution"]["technical_verdict"] == "PASS"
    assert case["acceptance"]["coverage"] == 1.0
    run_dir = tmp_path / "workspace" / "reports" / "ui-tests" / "e2e"
    assert (run_dir / case["evidence"]["html"]).is_file()
    assert Path(result["report"]).is_file()
    assert (run_dir / case["evidence"]["video"]).is_file()
    report_html = Path(result["report"]).read_text(encoding="utf-8")
    assert "<img" in report_html
    assert "<video" in report_html


def test_successful_structured_action_is_not_overridden_by_redundant_clicks(tmp_path: Path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TabsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cases = tmp_path / "cases.csv"
    with cases.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["name", "steps_text", "expected_text"])
        writer.writeheader()
        writer.writerow({"name": "TC1-页签", "steps_text": "切换待处理/执行中/全部页签",
                         "expected_text": "显示\"列表已加载\""})
    try:
        result = run(type("Args", (), {
            "cases": str(cases), "url": f"http://127.0.0.1:{server.server_port}/",
            "workspace": str(tmp_path / "workspace"), "session": None, "run_id": "tabs",
            "only": None, "allow_write": False, "headed": False, "timeout_ms": 10000,
            "wait_ms": 50,
        })())
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result["counts"] == {"PASS": 1}, repr(result)
    actions = result["cases"][0]["execution"]["actions_replayed"]
    assert [action["action"] for action in actions] == ["switch_tabs"]
    assert actions[0]["ok"] is True
