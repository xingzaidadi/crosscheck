"""接入编排器(通用、零业务):把已有的各路自发现(站点/登录/页面/库/源码契约)串成
一遍扫描,与当前 workspace 已配的槽位对比,产出"已知 vs 缺口"报告(gap_report)。

目标:接入一个新站点时,工具先扫一遍能查到的,只把查不到的列成缺口,交给交互层按清单
主动追问——用户不必自己想该给什么,也不必手写一堆 yaml。

分层(仿 bootstrap:纯函数可离线测 + 活部件可注入):
  纯函数:
    detect_login_method(fields)   登录页输入框特征 → 登录方式候选
    inspect_workspace(site,db)    读 workspace → 各槽位"已配?"布尔
    diff_gaps(known, have)        已扫到 vs 已配 → 缺口清单
    build_gap_report(known, have) 装配报告
  活部件(可注入,默认走真实浏览器/库/源码):
    scan_all(url, ...)            串起各路自发现 → gap_report 并落盘
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

# ── 登录方式探测(纯函数) ──
_PWD_TOKENS = ("password", "passwd", "pwd")
_SSO_TOKENS = ("sso", "oauth", "oidc", "saml", "cas", "ldap")
_PROXY_TOKENS = ("proxy", "onbehalf", "on-behalf", "actas", "act-as", "代办", "代登", "代替")


def detect_login_method(input_fields: list[dict], *, redirected_offsite: bool = False,
                        page_tokens: list[str] | None = None) -> dict:
    """登录页特征 → {method, confidence, signals, act_as_candidate}。
    input_fields: [{name,type,placeholder,id}...];page_tokens:页面按钮/链接文本(小写)。
    判据(通用,不认业务):
      有 SSO 标记 或 打开后跳到外站 → manual(第三方登录,人登一次最稳);
      有 password 框 + 文本框       → credential(声明式账密)候选;
      识别到代登/代办框             → 追加 act_as 信号(需确认代理账号);
      都不认识                      → manual(最稳兜底)。
    """
    fields = input_fields or []
    toks = {str(t).lower() for t in (page_tokens or [])}

    def _hay(f: dict) -> str:
        return " ".join(str(f.get(k, "")) for k in ("name", "type", "placeholder", "id")).lower()

    has_pwd = any("password" in str(f.get("type", "")).lower()
                  or any(t in _hay(f) for t in _PWD_TOKENS) for f in fields)
    has_text = any(str(f.get("type", "text")).lower() in ("text", "email", "tel", "")
                   for f in fields)
    sso = bool(redirected_offsite) or any(t in " ".join(toks) for t in _SSO_TOKENS) \
        or any(any(t in _hay(f) for t in _SSO_TOKENS) for f in fields)
    proxy = any(t in " ".join(toks) for t in _PROXY_TOKENS) \
        or any(any(t in _hay(f) for t in _PROXY_TOKENS) for f in fields)

    signals = []
    if has_pwd:
        signals.append("password-field")
    if sso:
        signals.append("sso")
    if proxy:
        signals.append("proxy-login")

    if sso:
        method, conf = "manual", 0.6
    elif has_pwd and has_text:
        method, conf = "credential", 0.75
    else:
        method, conf = "manual", 0.4
    return {"method": method, "confidence": conf, "signals": signals,
            "act_as_candidate": proxy}


# ── workspace 现状自省(纯读) ──
def _has_any_json(d: Path) -> bool:
    return d.is_dir() and any(d.glob("*.json"))


def inspect_workspace(site: str, db_name: str | None = None) -> dict:
    """读 workspace,判断各通用槽位是否已配。返回 {slot: bool}。纯读、零业务。"""
    from core.workspace import (workspace_root, profiles_dir, kb_dir, cases_dir)
    from core.config import db_params, site_credentials

    prof_path = profiles_dir() / f"{site}.yaml"
    login_mode = ""
    if prof_path.exists():
        try:
            import yaml
            login_mode = ((yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {})
                          .get("login") or {}).get("mode", "")
        except Exception:  # noqa: BLE001
            pass
    kb = kb_dir()
    return {
        "profile": prof_path.exists(),
        "login_mode": login_mode,
        "credentials": bool(site_credentials(site)),
        "accounts": (workspace_root() / "accounts" / f"{site}.yaml").exists(),
        "db_conn": db_params(db_name) is not None if db_name else False,
        "schema_map": _has_any_json(kb / "schema_map"),
        "contracts": _has_any_json(kb / "contracts"),
        "sitemap": (kb / "sitemap" / f"{site}.json").exists(),
        "query_mapping": _has_any_json(kb / "query_mapping"),
        "business_rules": (kb / "business_rules.json").exists(),
        "cases": cases_dir().is_dir() and any(cases_dir().iterdir()),
    }


# 固定收集清单(通用槽位 → 为什么问 / 交互层要问的面向用户话术)。
# 顺序即追问顺序。ask 用通用词,业务化措辞由 .claude/skills 的接入 skill 负责。
_SLOTS = [
    ("login_method", "登录方式关系到能否自动建登录态", "确认登录方式(人工登一次/声明式账密/第三方SSO)"),
    ("credentials", "声明式登录要账号口令(明文只落 gitignore 的 credentials.yaml)", "提供登录账号与口令"),
    ("role_accounts", "按角色取真人账号才能 act-as 走到对应环节", "各业务角色分别用哪个账号(可给候选人名)"),
    ("db_conn", "三方对账与反删要连库", "提供可连的库(读库对账、写库造数/清理)"),
    ("api_contracts", "有源码契约就能按字段/必填精确建模,不靠猜 body", "提供后端代码库路径(可选,强烈建议)"),
    ("page_catalog", "页面目录让走单/建模少逐页问", "确认要覆盖的页面(扫到的目录可勾选)"),
    ("case_source", "用例从哪来才能建模执行", "用例来源(Excel/文档/从契约派生)"),
    ("external_systems", "外部系统与事件触发口径扫不出,只能问", "涉及哪些外部系统、异步事件怎么触发"),
    ("business_rules_source", "判定口径类规则代码/库里读不出", "规则/口径文档在哪(PRD/技术方案)"),
]


def diff_gaps(known: dict, have: dict) -> list[dict]:
    """已扫到(known) vs 已配(have)→ 缺口清单。每条带扫到的候选当 scan_hint,让交互层问成选择题。"""
    login = known.get("login") or {}
    scanned = known.get("scan_errors") or {}
    satisfied = {
        "login_method": bool(have.get("profile")) and bool(have.get("login_mode")),
        # 账密:按"已配或扫到的方式"判——扫到 credential 却没账密=该问
        "credentials": bool(have.get("credentials"))
        or (have.get("login_mode") or login.get("method")) != "credential",
        "role_accounts": have.get("accounts"),
        "db_conn": have.get("db_conn"),
        "api_contracts": have.get("contracts") or bool(known.get("contracts")),
        "page_catalog": have.get("sitemap") or bool(known.get("pages")),
        "case_source": have.get("cases"),
        "external_systems": have.get("business_rules") or have.get("query_mapping"),
        "business_rules_source": have.get("business_rules"),
    }
    hints = {
        "login_method": (f"扫到登录方式候选={login.get('method')}(信号 {login.get('signals')})"
                         + ("+代登框" if login.get("act_as_candidate") else "")) if login else "",
        "api_contracts": (f"源码扫到 {len(known.get('contracts') or [])} 个端点契约"
                          if known.get("contracts") else (scanned.get("contracts") or "未提供代码库")),
        "page_catalog": (f"扫到 {len(known.get('pages') or [])} 个页面"
                         if known.get("pages") else (scanned.get("sitemap") or "")),
        "db_conn": scanned.get("db") or ("库已连通" if known.get("tables") else ""),
    }
    gaps = []
    for slot, why, ask in _SLOTS:
        if satisfied.get(slot):
            continue
        gaps.append({"slot": slot, "why": why, "ask": ask,
                     "scan_hint": hints.get(slot, "")})
    return gaps


def build_gap_report(known: dict, have: dict) -> dict:
    return {
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "site": known.get("site", ""),
        "known": known,
        "have": have,
        "gaps": diff_gaps(known, have),
    }


# ── 活部件:一遍扫描(各路可注入,任一路挂了只记成缺口、不崩) ──
def _safe(fn: Callable, *a, **k):
    try:
        return fn(*a, **k), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def scan_all(url: str, *, site: str | None = None, code_path: str | None = None,
             db_name: str | None = None, context: str = "", session_file: str | None = None,
             detect_fn: Callable[[str], tuple[str, list[str]]] | None = None,
             login_probe_fn: Callable[[str], dict] | None = None,
             sitemap_fn: Callable[..., dict] | None = None,
             db_factory: Callable[[str], Any] | None = None,
             contracts_fn: Callable[..., list] | None = None,
             write: bool = True) -> dict:
    """URL(+可选 代码库/库名)→ 串各路自发现 → gap_report。活部件默认走真实实现,全部可注入。"""
    from core.bootstrap import derive_site_and_base, detect_ui_kit, _default_detect
    from core import sitemap as _sitemap
    from core import dbmap as _dbmap
    from core.discovery import srcmap as _srcmap

    site0, base_url = derive_site_and_base(url)
    site = site or site0
    scan_errors: dict[str, str] = {}

    # 站点落地 + UI 套件
    detect = detect_fn or _default_detect
    det, err = _safe(detect, url)
    if err:
        scan_errors["detect"] = err
        final_url, classes = base_url, []
    else:
        final_url, classes = det
    kit = detect_ui_kit(classes)
    redirected = bool(final_url) and derive_site_and_base(final_url)[0] != site0

    # 登录方式:探登录页输入框
    login_detect = {"method": "manual", "confidence": 0.0, "signals": [], "act_as_candidate": False}
    probe = login_probe_fn or _default_login_probe
    lp, err = _safe(probe, final_url or base_url)
    if err:
        scan_errors["login"] = err
    elif lp:
        login_detect = detect_login_method(lp.get("input_fields") or [],
                                           redirected_offsite=redirected or lp.get("redirected_offsite", False),
                                           page_tokens=lp.get("page_tokens") or [])

    # 页面+接口目录
    pages: list[dict] = []
    sm_fn = sitemap_fn or _sitemap.discover
    sm, err = _safe(sm_fn, final_url or base_url, session_file)
    if err:
        scan_errors["sitemap"] = err
    elif sm:
        pages = sm.get("pages") or []

    # 库 schema(给了库名且能连)
    tables: dict = {}
    if db_name:
        db, err = _safe((db_factory or _default_db_factory), db_name)
        if err or not db:
            scan_errors["db"] = err or "无可连库(db.yaml 缺该库或为 TODO 占位)"
        else:
            mp, err2 = _safe(_dbmap.schema_map, db)
            if err2:
                scan_errors["db"] = err2
            else:
                tables = mp or {}

    # 源码契约(给了代码库)
    contracts: list = []
    if code_path:
        cf = contracts_fn or _srcmap.build_contracts
        cs, err = _safe(cf, code_path, context)
        if err:
            scan_errors["contracts"] = err
        else:
            contracts = cs or []

    known = {
        "site": site, "base_url": base_url, "final_url": final_url, "ui_kit": kit,
        "login": login_detect, "pages": pages,
        "api_count": sum(len(p.get("apis") or []) for p in pages),
        "tables": {t: tables[t] for t in list(tables)[:50]},
        "contracts": contracts, "scan_errors": scan_errors,
    }
    have = inspect_workspace(site, db_name)
    report = build_gap_report(known, have)
    if write:
        report["report_path"] = str(_write_report(site, report))
    return report


def _write_report(site: str, report: dict) -> Path:
    from core.workspace import workspace_root
    out = workspace_root() / "onboard" / f"{site}_gap_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _default_login_probe(login_url: str) -> dict:
    """活探登录页:开无痕浏览器,取输入框特征 + 可见按钮文本 + 是否跳外站。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context().new_page()
        try:
            pg.goto(login_url, wait_until="networkidle", timeout=45000)
        except Exception:  # noqa: BLE001
            pg.goto(login_url, wait_until="domcontentloaded")
        pg.wait_for_timeout(2500)
        final = pg.url
        fields = pg.evaluate(
            "() => Array.from(document.querySelectorAll('input,select')).slice(0,40)"
            ".map(e => ({name:e.name||'', type:e.type||e.tagName.toLowerCase(),"
            " placeholder:e.placeholder||'', id:e.id||''}))")
        toks = pg.evaluate(
            "() => Array.from(document.querySelectorAll('button,a,[class*=login],[class*=sso]'))"
            ".slice(0,60).map(e => (e.innerText||'').trim()).filter(Boolean)")
        b.close()
    from core.bootstrap import derive_site_and_base
    redirected = derive_site_and_base(final)[0] != derive_site_and_base(login_url)[0]
    return {"input_fields": fields, "page_tokens": toks, "redirected_offsite": redirected}


def _default_db_factory(db_name: str):
    """按 db.yaml 的库名建只读客户端;连不上/无配置 → None(上层记成缺口)。"""
    from core.config import db_params
    params = db_params(db_name)
    if not params:
        return None
    from db.client import DbClient
    return DbClient(readonly_params=params)

