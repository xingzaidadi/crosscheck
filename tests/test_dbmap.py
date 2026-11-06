"""
库映射(前置探索)验证(sqlite,离线、零业务):探出状态字段的真实取值。

跑:python tests/test_dbmap.py
"""
from __future__ import annotations

import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402

from core.dbmap import schema_map, state_values  # noqa: E402
from db.client import DbClient  # noqa: E402


def main():
    d = tempfile.mkdtemp()
    dbp = os.path.join(d, "s.db").replace("\\", "/")
    eng = create_engine(f"sqlite:///{dbp}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE ord_main (id INTEGER PRIMARY KEY, title TEXT, order_status TEXT)"))
        c.execute(text("CREATE TABLE ord_item (id INTEGER PRIMARY KEY, qty INT)"))  # 无状态字段
        for s in ["DRAFT", "SUBMITTED", "CLOSED", "DRAFT"]:
            c.execute(text("INSERT INTO ord_main (title, order_status) VALUES ('t',:s)"), {"s": s})
    eng.dispose()
    db = DbClient(dsn_readonly=f"sqlite:///{dbp}")

    print("库映射(前置探索)验证:\n")
    mp = schema_map(db, prefix="ord")
    assert set(mp.keys()) == {"ord_main", "ord_item"}, mp.keys()
    sv = mp["ord_main"]["state_fields"].get("order_status")
    assert sv and set(sv) == {"DRAFT", "SUBMITTED", "CLOSED"}, sv
    assert not mp["ord_item"]["state_fields"], "无状态字段的表不该编状态"
    print(f"    ✓ 探出 ord_main.order_status 真实取值: {sorted(sv)}(去重)")
    assert set(state_values(db, "ord_main", "order_status")) == {"DRAFT", "SUBMITTED", "CLOSED"}
    print("    ✓ state_values 单独取某状态字段的全部取值")
    print("\n全部通过 ✅  —— 库前置探索(表结构 + 状态字段真实取值)就位,状态机开工即知")


if __name__ == "__main__":
    main()
