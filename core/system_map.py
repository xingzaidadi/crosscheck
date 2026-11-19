"""Aggregate UI, API, database, role, state, and rule knowledge into one map."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.knowledge import KnowledgeBase


def _json_files(directory: Path) -> dict[str, Any]:
    values = {}
    if not directory.is_dir():
        return values
    for path in sorted(directory.glob("*.json")):
        try:
            values[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
    return values


def build_system_map(workspace: str | Path) -> dict[str, Any]:
    root = Path(workspace).resolve()
    knowledge_root = root / "knowledge_base"
    knowledge = KnowledgeBase(root).load()
    return {
        "workspace": str(root),
        "ui": {"sitemap": _json_files(knowledge_root / "sitemap"),
               "page_models": _json_files(knowledge_root / "page_model")},
        "api": _json_files(knowledge_root / "api_catalog"),
        "database": _json_files(knowledge_root / "schema_map"),
        "states": _json_files(knowledge_root / "state_recipes"),
        "knowledge": knowledge.records(),
    }


def write_system_map(workspace: str | Path, output: str | Path | None = None) -> Path:
    root = Path(workspace).resolve()
    path = Path(output).resolve() if output else root / "knowledge_base" / "system_map.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_system_map(root), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
