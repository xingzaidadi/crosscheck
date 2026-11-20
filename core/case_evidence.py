"""Ingest supporting project materials without turning them into manual config."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = {
    ".py", ".java", ".kt", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".cs",
    ".sql", ".yaml", ".yml", ".json", ".md", ".txt", ".xml", ".properties", ".ini",
    ".toml", ".csv", ".graphql", ".proto", ".http",
}
IGNORED_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "target", "__pycache__"}
SECRET_PATTERN = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+")


def _files(value: str | Path | None) -> list[Path]:
    if not value:
        return []
    root = Path(value).resolve()
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS
            and not any(part in IGNORED_DIRS for part in p.parts)]


def _signals(text: str, suffix: str) -> list[str]:
    lowered = text.lower()
    patterns = {
        "api_contract": ("openapi", "swagger", "@requestmapping", "@getmapping", "@postmapping", "/api/"),
        "database": ("create table", "alter table", "select ", "insert into", "数据库", "db.yaml"),
        "authorization": ("permission", "role", "scope", "权限", "角色", "越权"),
        "state_machine": ("status", "state", "状态", "审批", "approved", "rejected"),
        "validation": ("required", "maxlength", "校验", "必填", "正则", "validation"),
        "async": ("message", "mq", "kafka", "rabbit", "event", "异步", "队列"),
    }
    return [name for name, terms in patterns.items() if any(term in lowered for term in terms)]


def ingest_sources(values: list[str] | None, output: str | Path) -> dict[str, Any]:
    """Index code/design/database inputs as traceable evidence.

    This is deliberately read-only. It creates an inventory and short excerpts;
    later planners can use the inventory to enrich cases without executing source.
    """
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for value in values or []:
        for path in _files(value):
            try:
                raw = path.read_bytes()
                text = raw.decode("utf-8", errors="replace")
            except OSError as exc:
                records.append({"path": str(path), "status": "UNREADABLE", "error": str(exc)})
                continue
            records.append({
                "path": str(path), "relative_name": path.name, "extension": path.suffix.lower(),
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                "signals": _signals(text, path.suffix.lower()),
                "excerpt": SECRET_PATTERN.sub(r"\1=<redacted>", text[:1200]), "status": "INDEXED",
            })
    manifest = {"schema_version": 1, "source_count": len(records), "sources": records}
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
