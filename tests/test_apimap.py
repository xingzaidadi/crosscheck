"""
接口目录聚合 验证(离线、零业务):把 抓包/运行/站点发现 里见过的接口聚合去重。

跑:python tests/test_apimap.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.apimap import aggregate  # noqa: E402


def main():
    root = Path(tempfile.mkdtemp())
    caps = root / "captures"; runs = root / "runs"; site = root / "sitemap"
    (caps).mkdir(); (runs / "r1" / "cases" / "C1").mkdir(parents=True); site.mkdir()
    (caps / "f_picked.json").write_text(json.dumps({"method": "POST", "url": "https://h/api/list?a=1"}), encoding="utf-8")
    (runs / "r1" / "cases" / "C1" / "api_request.json").write_text(
        json.dumps({"method": "POST", "url": "https://h/api/submit", "body": {}}), encoding="utf-8")
    (site / "s.json").write_text(json.dumps({"pages": [{"apis": [{"method": "GET", "url": "https://h/api/detail/9"}]}]}), encoding="utf-8")

    print("接口目录聚合 验证:\n")
    cat = aggregate(caps, runs, site)
    keys = set(cat.keys())
    assert "POST /api/list" in keys and "POST /api/submit" in keys and "GET /api/detail/9" in keys, keys
    assert cat["POST /api/list"]["sources"] == ["capture"]
    assert cat["POST /api/submit"]["sources"] == ["run"]
    print(f"    ✓ 三处来源聚合去重,path 规整: {sorted(keys)}")
    print("\n全部通过 ✅  —— 接口目录聚合就位(已见接口的前置知识)")


if __name__ == "__main__":
    main()
