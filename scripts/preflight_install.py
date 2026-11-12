"""Check a fresh installation without touching a business workspace."""
from __future__ import annotations

import importlib
import sys

REQUIRED = ("playwright", "sqlalchemy", "pymysql", "yaml", "httpx", "openpyxl")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    if sys.version_info < (3, 10):
        print("ERROR: 需要 Python 3.10+")
        return 1
    missing = []
    for module in REQUIRED:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    if missing:
        print(f"ERROR: 缺少依赖: {', '.join(missing)}")
        print("  执行: python -m pip install -r requirements.txt")
        return 1
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except Exception as exc:
        print(f"ERROR: Chromium 未安装或无法启动: {exc}")
        print("  执行: python -m playwright install chromium")
        return 1
    print(f"OK: Python {sys.version.split()[0]}、依赖和 Chromium 均可用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
