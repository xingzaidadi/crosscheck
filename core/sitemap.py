"""
站点发现(通用):给一个根 URL(带登录态),自动爬出同站可测页面 + 各页触发的接口,
产出页面目录喂给建模——少问用户要东西(只给一个根 URL,不用逐页报)。

做法:打开根页 → 收导航候选(a[href]、菜单/页签、SPA 路由)→ 规整成同站绝对路由 →
逐个访问(有上限)→ 复用响应拦截抓每页的 XHR/fetch 接口 → 汇成 {page,url,apis} 目录。
目录落 workspace/knowledge_base/sitemap/<site>.json,供路由/建模取用。
normalize_routes 是纯函数(可离线测);discover 用 Playwright 实爬。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

_COLLECT_JS = r"""
() => {
  const out = [];
  const push = (text, href) => out.push({text: (text||'').trim().slice(0,40), href: href||''});
  document.querySelectorAll('a[href]').forEach(a => push(a.innerText, a.getAttribute('href')));
  document.querySelectorAll('[role=menuitem],[role=tab],[class*=menu-item],[class*=menu__item],[class*=tab]').forEach(e => {
    const h = e.getAttribute('href') || e.getAttribute('data-href') || e.getAttribute('data-route') || '';
    push(e.innerText, h);
  });
  return out;
}
"""

# SPA 导航多为无 href 的 div/按钮:收"可点的导航项文本"(菜单/侧边/页签,含折叠子菜单),交互式发现用。
# 含当前隐藏的子菜单项(在 DOM 里),过滤"收起/展开"等噪音;点不到的点击时自然跳过。
_NAV_NOISE = ("收起", "展开", "折叠", "全部", "更多", "collapse", "expand", "more")
_NAV_TEXT_JS = r"""
(noise) => {
  const sel = '[role=menuitem],[role=tab],[class*=menu] li,[class*=menu] a,[class*=submenu] li,'
            + '[class*=sider] li,[class*=nav] li,[class*=tab-pane],[class*=tab] [class*=title]';
  const seen = new Set(); const out = [];
  document.querySelectorAll(sel).forEach(e => {
    // 取叶子项文本:优先无子 li 的节点,避免把整组菜单文本连在一起
    if (e.querySelector('li,[class*=submenu]')) return;
    const t = (e.innerText||'').trim();
    if (!t || t.length > 16 || seen.has(t)) return;
    if (noise.some(n => t.includes(n))) return;
    seen.add(t); out.push(t);
  });
  return out.slice(0, 60);
}
"""


def normalize_routes(hrefs: list[str], base_url: str) -> list[str]:
    """候选 href → 同站绝对路由(去外链/锚点/js:,保 SPA #/路由,去重保序)。纯函数。"""
    base_host = urlparse(base_url).netloc
    out, seen = [], set()
    for h in hrefs:
        if not h:
            continue
        h = h.strip()
        low = h.lower()
        if low.startswith(("javascript:", "mailto:", "tel:", "data:")):
            continue
        if h in ("#", "/#", ""):
            continue
        absu = urljoin(base_url, h)
        pu = urlparse(absu)
        if pu.netloc and pu.netloc != base_host:   # 外站
            continue
        if absu in seen:
            continue
        seen.add(absu)
        out.append(absu)
    return out


def discover(root_url: str, session_file: str | None = None, *, max_pages: int = 12,
             url_pattern: str = "", headless: bool = True, wait_ms: int = 2500) -> dict:
    """从根 URL 爬一层:收候选路由 → 逐个访问抓接口 → 返回 {root, pages:[{title,url,apis}]}。"""
    from playwright.sync_api import sync_playwright

    pages_out, apis_by_url = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx_kw = {"viewport": {"width": 1440, "height": 900}}
        if session_file and Path(session_file).exists():
            ctx_kw["storage_state"] = session_file
        ctx = browser.new_context(**ctx_kw)
        page = ctx.new_page()

        cur = {"url": None}

        def on_resp(resp):
            try:
                req = resp.request
                if req.resource_type not in ("xhr", "fetch"):
                    return
                if url_pattern and url_pattern not in resp.url:
                    return
                apis_by_url.setdefault(cur["url"], [])
                sig = (req.method, urlparse(resp.url).path)
                if sig not in {(a["method"], a["path"]) for a in apis_by_url[cur["url"]]}:
                    apis_by_url[cur["url"]].append(
                        {"method": req.method, "path": urlparse(resp.url).path, "url": resp.url})
            except Exception:  # noqa: BLE001
                pass
        ctx.on("response", on_resp)

        cur["url"] = root_url
        try:
            page.goto(root_url, wait_until="networkidle", timeout=30000)
        except Exception:  # noqa: BLE001
            page.goto(root_url, wait_until="domcontentloaded")
        page.wait_for_timeout(wait_ms)
        cands = page.evaluate(_COLLECT_JS)
        routes = normalize_routes([c["href"] for c in cands], root_url)[:max_pages]

        for u in routes:
            cur["url"] = u
            try:
                page.goto(u, wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(wait_ms)
                title = page.title()
            except Exception:  # noqa: BLE001
                title = ""
            pages_out.append({"title": title, "url": u, "apis": apis_by_url.get(u, [])})

        # 交互式发现(SPA 菜单无 href):点每个导航项,记点击后的真实 URL + 触发的接口
        seen = {p["url"] for p in pages_out}
        try:
            navs = page.evaluate(_NAV_TEXT_JS, list(_NAV_NOISE))
        except Exception:  # noqa: BLE001
            navs = []
        for t in navs[:max_pages]:
            try:
                page.goto(root_url, wait_until="domcontentloaded")
                page.wait_for_timeout(1200)
                cur["url"] = f"nav:{t}"
                page.get_by_text(t, exact=True).first.click(timeout=4000)
                page.wait_for_timeout(wait_ms)
                real = page.url
                apis = apis_by_url.pop(f"nav:{t}", [])
                # 只记"点击后 URL 真变了"的(排除 收起/切tab 这类不导航的噪音)
                if real and real != root_url and real not in seen:
                    seen.add(real)
                    pages_out.append({"title": page.title(), "url": real, "nav": t, "apis": apis})
            except Exception:  # noqa: BLE001
                pass

        ctx.close(); browser.close()
    return {"root": root_url, "discovered_at": time.strftime("%Y-%m-%d %H:%M:%S"), "pages": pages_out}


def save_sitemap(site: str, catalog: dict) -> Path:
    from core.workspace import kb_dir
    path = kb_dir() / "sitemap" / f"{site}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
