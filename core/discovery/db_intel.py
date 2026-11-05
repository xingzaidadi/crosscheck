"""
库约束探针(通用,任意表):从 schema 读出"哪些列必填、合法枚举、类型",再抽老数据当样例值。
给自发现提供"该填什么值"的硬约束来源之一(前端校验之外的补充)。
"""
from __future__ import annotations

import re
from typing import Any

from db.client import DbClient

_ENUM_RE = re.compile(r"(?:enum|set)\((.*)\)", re.I)


def _parse_enum(column_type: str) -> list[str]:
    m = _ENUM_RE.search(column_type or "")
    if not m:
        return []
    return [x.strip().strip("'\"") for x in m.group(1).split(",")]


def table_constraints(db: DbClient, table: str) -> dict[str, dict[str, Any]]:
    """
    返回 {列名: {required, type, enum:[...], default, auto}}。
      required = NOT NULL 且无默认值且非自增(= 建数据必须给的列)。
    """
    out: dict[str, dict] = {}
    if db.dialect == "sqlite":
        for r in db.query(f"PRAGMA table_info({table})"):
            out[r["name"]] = {
                "type": r["type"], "enum": [],
                "default": r["dflt_value"],
                "auto": bool(r["pk"]),
                "required": bool(r["notnull"]) and r["dflt_value"] is None and not r["pk"],
            }
        return out
    rows = db.query(
        "SELECT COLUMN_NAME AS name, IS_NULLABLE AS nullable, DATA_TYPE AS dtype, "
        "COLUMN_TYPE AS ctype, COLUMN_DEFAULT AS dflt, EXTRA AS extra "
        "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
        "ORDER BY ORDINAL_POSITION", {"t": table})
    for r in rows:
        auto = "auto_increment" in (r.get("extra") or "").lower()
        out[r["name"]] = {
            "type": r["dtype"], "enum": _parse_enum(r.get("ctype") or ""),
            "default": r.get("dflt"), "auto": auto,
            "required": (r["nullable"] == "NO") and r.get("dflt") is None and not auto,
        }
    return out


def sample_values(db: DbClient, table: str, cols: list[str], where: str = "1=1", n: int = 5
                  ) -> dict[str, list]:
    """抽老数据里各列的常见非空取值,给'该填什么'当真实样例。"""
    out: dict[str, list] = {}
    for c in cols:
        try:
            rows = db.query(
                f"SELECT {c} AS v, COUNT(*) AS n FROM {table} WHERE {where} AND {c} IS NOT NULL "
                f"GROUP BY {c} ORDER BY n DESC LIMIT {int(n)}")
            out[c] = [r["v"] for r in rows]
        except Exception:  # noqa: BLE001
            out[c] = []
    return out
