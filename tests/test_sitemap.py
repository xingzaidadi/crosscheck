"""
站点发现 — 路由规整 验证(纯函数,离线、零业务)。
给一堆候选 href,规整成"同站绝对路由":去外链/锚点/js:,保 SPA #/路由,去重保序。

跑:python tests/test_sitemap.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.sitemap import normalize_routes  # noqa: E402


def main():
    print("站点发现 路由规整 验证:\n")
    base = "https://app.test/portal"
    hrefs = ["/list", "https://ext.com/x", "#/spa/detail", "#", "javascript:void(0)",
             "/list", "mailto:a@b.c", "https://app.test/accept", "sub/page"]
    routes = normalize_routes(hrefs, base)
    assert "https://app.test/list" in routes
    assert "https://app.test/accept" in routes
    assert "https://app.test/portal#/spa/detail" in routes      # SPA 路由保留
    assert "https://app.test/sub/page" in routes                # 相对路径转绝对
    assert not any("ext.com" in r for r in routes), "外站应去掉"
    assert not any(r.endswith("#") for r in routes)             # 裸锚点去掉
    assert not any("javascript" in r or "mailto" in r for r in routes)
    assert routes.count("https://app.test/list") == 1           # 去重
    print(f"    ✓ 同站 {len(routes)} 条:相对转绝对、SPA #/路由保留、外链/锚点/js:/mailto 去掉、去重保序")
    print(f"      {routes}")
    print("\n全部通过 ✅  —— 站点发现路由规整就位(给一个根URL,爬出同站可测页面的基础)")


if __name__ == "__main__":
    main()
