"""Preflight 环境自发现编排器(通用、零业务):从一个 Site Profile 把现有发现库跑成一趟,
产出一张"能力就绪图"(哪些探到了、哪些缺、落在哪)。只做按序调用 + 汇总,不认识任何业务。

能力维度(可 --only 子集):
  db   —— dbmap.schema_map:库结构 + 状态字段真实取值      (需只读库连接)
  api  —— apimap.build:历史流量聚合成接口目录            (离线聚合文件)
  site —— sitemap.discover:爬页面 + 抓接口 + 请求体样本    (需登录态/浏览器)
各维度独立 try,一个失败不拖垮其余;结果写 knowledge_base/readiness/<site>.json。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable


def _sweep_db(profile, db=None) -> dict:
    from core import dbmap
    close = False
    if db is None:
        from core.config import db_params
        from db.client import DbClient
        name = profile.db_readonly
        p = db_params(name) if name else None
        if not p:
            return {"ok": False, "missing": "profile 未配只读库(db.readonly),跳过库结构发现"}
        db = DbClient(readonly_params=p)
        close = True
    try:
        mp = dbmap.schema_map(db)
        name = profile.db_readonly or profile.site
        dbmap.save_schema_map(name, mp)
        from core.workspace import kb_dir
        path = kb_dir() / "schema_map" / f"{name}.json"
        ntables = len(mp) if isinstance(mp, dict) else 0
        return {"ok": True, "source_path": str(path), "detail": f"{ntables} 表"}
    finally:
        if close:
            db.close()


def _sweep_api(profile) -> dict:
    from core import apimap
    out = apimap.build(profile.site)
    try:
        cat = json.loads(Path(out).read_text(encoding="utf-8"))
        n = len(cat) if isinstance(cat, (list, dict)) else 0
    except Exception:  # noqa: BLE001
        n = 0
    return {"ok": True, "source_path": str(out), "detail": f"{n} 接口"}


def _sweep_site(profile, *, max_pages: int = 10, headless: bool = True) -> dict:
    from core import sitemap
    if not profile.base_url:
        return {"ok": False, "missing": "profile 未配 base_url,跳过站点发现"}
    sess = profile.session_file if Path(profile.session_file).exists() else None
    cat = sitemap.discover(profile.base_url, session_file=sess, max_pages=max_pages, headless=headless)
    out = sitemap.save_sitemap(profile.site, cat)
    return {"ok": True, "source_path": str(out), "detail": f"session={'有' if sess else '无(仅公开页)'}"}


DEFAULT_SWEEPS: dict[str, Callable] = {"db": _sweep_db, "api": _sweep_api, "site": _sweep_site}


def write_capability_map(site: str, steps: dict) -> Path:
    from core.workspace import kb_dir
    out = kb_dir() / "readiness" / f"{site}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(steps, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def run_preflight(profile, *, only: set[str] | None = None, force: bool = False,
                  sweeps: dict[str, Callable] | None = None) -> dict:
    """跑发现一趟,返回 {site, base_url, ts, steps:{dim:{ok,...}}},并落 readiness/<site>.json。
    sweeps 可注入(测试/定制);默认 DEFAULT_SWEEPS。only 选子集。"""
    sweeps = sweeps or DEFAULT_SWEEPS
    want = (lambda k: True) if not only else (lambda k: k in only)
    steps: dict[str, Any] = {}
    for dim, fn in sweeps.items():
        if not want(dim):
            continue
        try:
            steps[dim] = fn(profile)
        except Exception as e:  # noqa: BLE001  单维度失败不拖垮整体
            steps[dim] = {"ok": False, "missing": f"探测异常: {str(e)[:120]}"}
    result = {"site": profile.site, "base_url": profile.base_url,
              "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "steps": steps}
    write_capability_map(profile.site, result)
    return result
