"""残留哨兵(通用、零业务):跑后扫各表的标记列,揪出"本该清掉却留下"的造数行。
数据隔离的收口:marker 前缀命中但不在保留白名单里的,即泄漏。业务只给(表,标记列)清单 + 白名单。
"""
from __future__ import annotations

from typing import Any


def scan_residue(db, tables_with_markercol: list[tuple[str, str]], *,
                 prefix: str = "AUTOTEST", keep: list[str] | None = None) -> list[dict[str, Any]]:
    """扫 [(表, 标记列)],找标记列以 prefix 开头、且不在 keep 白名单的残留。返回 [{table,column,value}]。只读。"""
    keepset = set(keep or [])
    leaked: list[dict[str, Any]] = []
    for table, col in tables_with_markercol:
        try:
            rows = db.query(f"SELECT DISTINCT {col} AS v FROM {table} WHERE {col} LIKE :p", {"p": f"{prefix}%"})
        except Exception:  # noqa: BLE001  查不到(无表/无列)跳过,不误报
            continue
        for r in rows:
            v = r.get("v")
            if v and v not in keepset:
                leaked.append({"table": table, "column": col, "value": v})
    return leaked
