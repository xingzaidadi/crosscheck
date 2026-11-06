"""
接口目录(前置探索的另一半):把已见过的接口(历次抓包/运行证据/站点发现)聚合成一张
method+path 目录,作为建模时"调哪个接口"的知识库——减少临场问人。

来源:captures/*_picked.json、runs/*/cases/*/api_request.json、knowledge_base/sitemap/*.json。
注:**动作类接口(驳回/受理/关闭)只有被执行过才会出现在流量里**;要补齐需一次"演练/录制",
库里是没有接口信息的——这是接口侧前置探索的诚实边界。
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


def _add(cat: dict, method: str, url: str, source: str):
    if not url:
        return
    path = urlparse(url).path or url
    key = f"{(method or 'GET').upper()} {path}"
    e = cat.setdefault(key, {"method": (method or "GET").upper(), "path": path, "seen": 0, "sources": set()})
    e["seen"] += 1
    e["sources"].add(source)


def aggregate(captures_dir: Path, runs_dir: Path, sitemap_dir: Path) -> dict:
    """扫三处已见流量,聚合成 {‘METHOD /path’: {method,path,seen,sources}}。"""
    cat: dict = {}
    for f in Path(captures_dir).glob("*_picked.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            _add(cat, d.get("method"), d.get("url"), "capture")
        except Exception:  # noqa: BLE001
            pass
    for f in Path(runs_dir).glob("*/cases/*/api_request.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            _add(cat, d.get("method"), d.get("url"), "run")
        except Exception:  # noqa: BLE001
            pass
    for f in Path(sitemap_dir).glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            for pg in d.get("pages", []):
                for a in pg.get("apis", []):
                    _add(cat, a.get("method"), a.get("url") or a.get("path"), "sitemap")
        except Exception:  # noqa: BLE001
            pass
    for e in cat.values():
        e["sources"] = sorted(e["sources"])
    return cat


def build(db_name: str = "ebuy-demand") -> Path:
    from core.workspace import captures_dir, workspace_root, kb_dir
    cat = aggregate(captures_dir(), workspace_root() / "runs", kb_dir() / "sitemap")
    out = kb_dir() / "api_catalog" / f"{db_name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(list(cat.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    return out
