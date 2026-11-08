"""角色能力自发现(通用、零业务):给 N 个角色的登录态,各自跑一遍发现,得出每个角色
"实际够得到的接口/路由"集合;角色间取差集即知谁能做什么。喂给就绪门禁判"缺角色账号"。

不认识任何角色名——角色就是调用方给的键(bootstrap 收集)。能力 = 从该角色会话的站点
发现产物里扫出的所有 /path(接口或导航),schema 无关(递归扫字符串里的 path)。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from core.readiness import _PATH, norm_endpoint

_HOST = re.compile(r"https?://[^/\s]+")


def caps_from_catalog(cat: Any) -> set[str]:
    """从任意站点发现产物(dict/list 嵌套)里递归扫出所有 /path 能力,规整去重。schema 无关。
    先剥掉内嵌的 scheme://host,避免把主机名当成 path 首段(/h/app → /app)。"""
    caps: set[str] = set()

    def walk(o):
        if isinstance(o, str):
            for m in _PATH.findall(_HOST.sub("", o)):
                caps.add(norm_endpoint(m))
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    walk(cat)
    return {c for c in caps if c}


def _default_probe(root_url: str, session_file: str, *, max_pages: int = 6, headless: bool = True) -> set[str]:
    """默认探法:复用 sitemap.discover 在该角色会话下爬几页 + 抓接口,扫出能力集。"""
    from core.sitemap import discover
    cat = discover(root_url, session_file=session_file, max_pages=max_pages, headless=headless)
    return caps_from_catalog(cat)


def build_rolemap(role_state_paths: dict[str, str | Path], *, root_url: str,
                  probe_fn: Callable[..., set[str]] | None = None, **probe_kw) -> dict[str, list[str]]:
    """逐角色探能力集 → {role: [caps]}。probe_fn 可注入(测试/离线);默认用 sitemap 探。"""
    probe = probe_fn or _default_probe
    mp: dict[str, list[str]] = {}
    for role, state in role_state_paths.items():
        try:
            caps = probe(root_url, str(state), **probe_kw)
        except Exception:  # noqa: BLE001  某角色探失败不拖垮整体,记空集
            caps = set()
        mp[role] = sorted(caps)
    return mp


def union_reachable(rolemap: dict[str, list[str]]) -> set[str]:
    """所有角色能力并集 = 当前这套账号整体够得到的接口(喂 readiness.Capabilities.reachable)。"""
    out: set[str] = set()
    for caps in rolemap.values():
        out |= set(caps)
    return out


def unique_per_role(rolemap: dict[str, list[str]]) -> dict[str, list[str]]:
    """每个角色独有(别的角色都没有)的能力 —— 直观看出角色边界。"""
    roles = {r: set(c) for r, c in rolemap.items()}
    out = {}
    for r, caps in roles.items():
        others: set[str] = set()
        for rr, cc in roles.items():
            if rr != r:
                others |= cc
        out[r] = sorted(caps - others)
    return out


def save_rolemap(site: str, mp: dict) -> Path:
    from core.workspace import kb_dir
    out = kb_dir() / "rolemap" / f"{site}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(mp, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_rolemap(site: str) -> dict[str, list[str]]:
    from core.workspace import kb_dir
    p = kb_dir() / "rolemap" / f"{site}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
