"""
库映射(前置探索的一部分):开工先把库探一遍,建一张"系统知识地图"——全表结构 +
每个状态/类型字段的**真实取值枚举**(从数据 DISTINCT 出来)+ schema 枚举约束。
这样"有哪些状态、怎么到终态/驳回态"开工就知道,执行用例时不再走一步卡一步问人。
纯内省只读,不改数据;落 workspace/knowledge_base/schema_map/<db>.json 供建模取用。
"""
from __future__ import annotations

import json

_STATE_HINT = ("status", "state", "stage", "type", "mode", "flag", "kind")


def schema_map(db, prefix: str = "", max_values: int = 40) -> dict:
    """全表(可按前缀过滤)→ {table: {columns, enums, state_fields:{列: [真实取值]}}}。"""
    from core.discovery.db_intel import table_constraints
    out = {}
    for t in db.tables():
        if prefix and not t.startswith(prefix):
            continue
        try:
            cons = table_constraints(db, t)
        except Exception:  # noqa: BLE001
            continue
        enums, states = {}, {}
        for c, m in cons.items():
            if m.get("enum"):
                enums[c] = m["enum"]
            low = c.lower()
            if any(k in low for k in _STATE_HINT):
                try:
                    rows = db.query(
                        f"SELECT DISTINCT {c} AS v FROM {t} WHERE {c} IS NOT NULL AND {c}<>'' LIMIT {int(max_values)}")
                    vals = [r["v"] for r in rows]
                    if vals:
                        states[c] = vals
                except Exception:  # noqa: BLE001
                    pass
        out[t] = {"columns": list(cons.keys()), "enums": enums, "state_fields": states}
    return out


def save_schema_map(db_name: str, mp: dict):
    from core.workspace import kb_dir
    p = kb_dir() / "schema_map" / f"{db_name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(mp, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def state_values(db, table: str, column: str, max_values: int = 40) -> list:
    """某状态字段的真实取值(状态机地图)。"""
    rows = db.query(
        f"SELECT DISTINCT {column} AS v FROM {table} WHERE {column} IS NOT NULL AND {column}<>'' LIMIT {int(max_values)}")
    return [r["v"] for r in rows]
