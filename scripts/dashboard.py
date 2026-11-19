"""Render or serve the local Crosscheck dashboard."""
from __future__ import annotations

import argparse
import os
import sys
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.control_plane import render_dashboard  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="生成或启动 Crosscheck 本地管理控制台")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    path = render_dashboard(args.workspace)
    print(path)
    if not args.serve:
        return 0
    os.chdir(Path(args.workspace).resolve())
    server = ThreadingHTTPServer(("127.0.0.1", args.port), SimpleHTTPRequestHandler)
    print(f"http://127.0.0.1:{args.port}/dashboard.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
