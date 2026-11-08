"""多步向导枚举自发现(通用、零业务):有些入口是"多步选择",后一步的选项依赖前面所选
(选组织→选场景→选模板……),手工穷举既累又易漏。envmap 把它抽象成一棵选择树:
给定"某前缀选择下有哪些下一步选项"的函数,机器枚举所有 根→叶 的可达路径。

core 不认识任何业务:每步有哪些选项由 options_fn 给(活态=驱动页面读当前选项;离线=喂假树)。
产出可达配置清单,供用例参数化(对真实可达组合各跑一遍),不再写死某条路径。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def enumerate_paths(options_fn: Callable[[list], list], *,
                    max_paths: int = 200, max_depth: int = 12) -> list[list]:
    """DFS 枚举根→叶路径。options_fn(prefix) 返回该前缀下的下一步选项列表;返回 [] 即叶子。
    封顶 max_paths/max_depth 防爆。选项可为任意可序列化 token(str 或 {label,value})。"""
    out: list[list] = []

    def dfs(prefix: list):
        if len(out) >= max_paths or len(prefix) >= max_depth:
            if prefix:
                out.append(list(prefix))
            return
        opts = options_fn(prefix) or []
        if not opts:
            if prefix:
                out.append(list(prefix))
            return
        for o in opts:
            if len(out) >= max_paths:
                break
            dfs(prefix + [o])

    dfs([])
    return out[:max_paths]


def build_envmap(site: str, wizard_key: str, options_fn: Callable[[list], list], **kw) -> dict:
    """枚举一个向导并落盘 kb/envmap/<site>/<wizard_key>.json。返回 {ok, paths, count}。"""
    try:
        paths = enumerate_paths(options_fn, **kw)
        save_envmap(site, wizard_key, paths)
        return {"ok": True, "count": len(paths), "paths": paths}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "missing": f"枚举异常: {str(e)[:100]}"}


def save_envmap(site: str, wizard_key: str, paths: list[list]) -> Path:
    from core.workspace import kb_dir
    out = kb_dir() / "envmap" / site / f"{wizard_key}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"paths": paths}, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_envmap(site: str, wizard_key: str) -> list[list]:
    from core.workspace import kb_dir
    p = kb_dir() / "envmap" / site / f"{wizard_key}.json"
    return (json.loads(p.read_text(encoding="utf-8")).get("paths") or []) if p.exists() else []
