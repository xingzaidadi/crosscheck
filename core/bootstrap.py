"""极简自举(通用、零业务):用户只给一个 URL + 浏览器登一次,工具自动识别并**替用户写好**
Site Profile,不用手写任何 yaml。

可测纯函数:
  derive_site_and_base(url)      URL → (site, base_url)
  detect_ui_kit(class_names)     落地页 class 前缀直方图 → {kit, confidence, top}
  build_profile(...)             装配 profile dict
  write_profile / write_accounts 落盘
活部件(可注入,默认走真实浏览器/登录):
  bootstrap(url, roles, *, detect_fn=None, login_fn=None)
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

# 工具类/原子化框架的高频前缀,不算 UI 套件命名空间(避免被 tailwind 之类带偏)
_UTILITY = {"flex", "grid", "text", "min", "max", "w", "h", "p", "m", "bg", "border",
            "rounded", "items", "justify", "gap", "font", "overflow", "absolute", "relative"}


def derive_site_and_base(url: str) -> tuple[str, str]:
    """https://shop.test.example.cn/a/b → (site='shop', base_url='https://shop.test.example.cn')。
    site 取主机首标签(纯通用:不含任何业务语义,只是个工作区键)。"""
    u = urlsplit(url if "://" in url else "https://" + url)
    base = f"{u.scheme or 'https'}://{u.netloc}"
    host = u.hostname or "site"
    first = host.split(".")[0]
    site = "".join(ch for ch in first if ch.isalnum() or ch in "-_") or "site"
    return site, base


def _tokens(class_names: list[str]) -> list[str]:
    out = []
    for c in class_names or []:
        for tok in str(c).split():
            tok = tok.strip()
            if tok:
                out.append(tok)
    return out


def detect_ui_kit(class_names: list[str]) -> dict:
    """统计组件类(含 '-' 且首段非工具类)的首段前缀,取主导者当 UI 套件键。
    返回 {kit, confidence, top:[(prefix,count)...]}。无主导 → kit='generic'。"""
    toks = _tokens(class_names)
    counter: Counter = Counter()
    for t in toks:
        if "-" not in t:
            continue
        head = t.split("-")[0]
        if not head or head.lower() in _UTILITY:
            continue
        counter[head] += 1
    if not counter:
        return {"kit": "generic", "confidence": 0.0, "top": []}
    total = sum(counter.values())
    top = counter.most_common(5)
    kit, n = top[0]
    return {"kit": kit, "confidence": round(n / total, 3), "top": top}


def build_profile(site: str, base_url: str, *, ui_kit: str = "generic",
                  auth_mode: str = "manual", login_url: str = "",
                  liveness_url: str = "", logged_in_selector: str = "",
                  db_readonly: str | None = None) -> dict:
    """装配 profile dict(结构与 core.profile._coerce 吃的一致)。业务值由探测/对话填,结构通用。"""
    prof: dict[str, Any] = {
        "site": site,
        "base_url": base_url,
        "login": {"mode": auth_mode, "login_url": login_url or base_url},
        "defaults": {"ui_kit": ui_kit, "launch_mode": "isolated"},
    }
    if liveness_url:
        prof["login"]["liveness_url"] = liveness_url
    if logged_in_selector:
        prof["login"]["logged_in_selector"] = logged_in_selector
    if db_readonly:
        prof["db"] = {"readonly": db_readonly}
    return prof


def write_profile(site: str, profile_dict: dict) -> Path:
    import yaml
    from core.workspace import profiles_dir
    out = profiles_dir() / f"{site}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(profile_dict, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return out


def write_accounts(site: str, roles: dict[str, str]) -> Path:
    """roles: {角色键: 登录态文件路径}。落 workspace/accounts/<site>.yaml,供 rolemap/执行选账号。"""
    import yaml
    from core.workspace import workspace_root
    out = workspace_root() / "accounts" / f"{site}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump({"site": site, "roles": roles}, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    return out


def _default_detect(url: str) -> tuple[str, list[str]]:
    """活探:开无痕浏览器打开 url,取落地页 url + 所有元素的 class。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context().new_page()
        pg.goto(url, wait_until="networkidle", timeout=45000)
        pg.wait_for_timeout(3000)
        final_url = pg.url
        classes = pg.evaluate(
            "() => Array.from(document.querySelectorAll('[class]')).slice(0,4000).map(e => e.getAttribute('class'))")
        b.close()
    return final_url, classes


def bootstrap(url: str, roles: list[str] | None = None, *,
              detect_fn: Callable[[str], tuple[str, list[str]]] | None = None,
              login_fn: Callable[[str, str], str] | None = None,
              db_readonly: str | None = None) -> dict:
    """URL → 自动识别 + 每角色登一次 → 写 profiles/<site>.yaml + accounts/<site>.yaml。
    detect_fn / login_fn 可注入(测试/定制);默认走真实浏览器与 login.ensure_session(manual)。"""
    roles = roles or ["default"]
    site, base_url = derive_site_and_base(url)
    detect = detect_fn or _default_detect
    final_url, classes = detect(url)
    kit = detect_ui_kit(classes)
    auth_mode = "manual"  # 默认人登一次,最通用(SSO/2FA 都兼容);凭据式留作后续
    login_url = final_url or base_url

    prof = build_profile(site, base_url, ui_kit=kit["kit"], auth_mode=auth_mode,
                         login_url=login_url, db_readonly=db_readonly)
    profile_path = write_profile(site, prof)

    # 每角色登一次,存各自登录态
    login = login_fn or _default_login
    role_states: dict[str, str] = {}
    for role in roles:
        role_states[role] = str(login(site, role))
    accounts_path = write_accounts(site, role_states)

    return {"site": site, "base_url": base_url, "ui_kit": kit,
            "profile_path": str(profile_path), "accounts_path": str(accounts_path),
            "roles": role_states}


def _default_login(site: str, role: str) -> str:
    """活登:复用 login.ensure_session(manual) 弹浏览器,人登一次。
    多角色:每角色一份登录态——default 用 .auth/<site>.json,其余用 .auth/<site>__<role>.json。"""
    from core.profile import load_profile
    from core.login import ensure_session
    from core.workspace import auth_dir
    prof = load_profile(site)
    target = str(auth_dir() / (f"{site}.json" if role in ("default", "") else f"{site}__{role}.json"))
    return ensure_session(prof, force=False, session_file=target)
