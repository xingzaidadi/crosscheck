"""Run a self-contained browser -> HTTP API -> SQLite verification demo."""
from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HTML = """<!doctype html><meta charset=utf-8><title>Crosscheck Demo</title>
<label>Item name <input id=itemName></label><button id=create>Create</button><p id=result></p>
<script>
create.onclick=async()=>{const r=await fetch('/api/items',{method:'POST',headers:{'content-type':'application/json'},
body:JSON.stringify({name:itemName.value})});const x=await r.json();result.textContent='Created '+x.name;};
</script>"""


class DemoHandler(BaseHTTPRequestHandler):
    database: Path

    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        payload = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path != "/api/items":
            self.send_error(404)
            return
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        name = str(body.get("name") or "")
        if not name.startswith("AUTOTEST_"):
            self.send_error(400, "demo requires AUTOTEST_ marker")
            return
        connection = sqlite3.connect(self.database)
        try:
            cursor = connection.execute("INSERT INTO items(name) VALUES (?)", (name,))
            connection.commit()
            item_id = cursor.lastrowid
        finally:
            connection.close()
        payload = json.dumps({"id": item_id, "name": name}).encode("utf-8")
        self.send_response(201)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run_demo(workspace: Path) -> dict:
    from playwright.sync_api import sync_playwright

    workspace.mkdir(parents=True, exist_ok=True)
    database = workspace / "demo.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
        connection.execute("DELETE FROM items")
        connection.commit()
    finally:
        connection.close()
    DemoHandler.database = database
    server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    marker = "AUTOTEST_LOCAL_DEMO"
    response_data = {}
    screenshot = workspace / "demo.png"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/")
                page.locator("#itemName").fill(marker)
                with page.expect_response(lambda response: response.url.endswith("/api/items")) as response_info:
                    page.locator("#create").click()
                response = response_info.value
                response_data.update({"status": response.status, "body": response.json()})
                page.locator("#result").filter(has_text=f"Created {marker}").wait_for()
                page.screenshot(path=str(screenshot))
            finally:
                browser.close()
        connection = sqlite3.connect(database)
        try:
            row = connection.execute("SELECT id,name FROM items WHERE name=?", (marker,)).fetchone()
            connection.execute("DELETE FROM items WHERE name=?", (marker,))
            connection.commit()
            residue = connection.execute("SELECT COUNT(*) FROM items WHERE name=?", (marker,)).fetchone()[0]
        finally:
            connection.close()
        passed = response_data.get("status") == 201 and row and row[1] == marker and residue == 0
        result = {"passed": bool(passed), "ui": {"screenshot": str(screenshot)},
                  "api": response_data, "db": {"row": row, "residue": residue}}
        (workspace / "demo-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="运行本地 UI/API/SQLite 全链路演示")
    parser.add_argument("--workspace")
    args = parser.parse_args()
    if args.workspace:
        target = Path(args.workspace).resolve()
        result = run_demo(target)
    else:
        with tempfile.TemporaryDirectory(prefix="crosscheck-demo-") as directory:
            target = Path(directory)
            result = run_demo(target)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["passed"] else 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"demo artifacts: {target}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
