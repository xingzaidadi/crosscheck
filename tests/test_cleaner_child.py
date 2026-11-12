"""
通用 Cleaner 子表按父单号清理 验证(sqlite,离线)。

证明:标记只落在父表(父单标题),子表只有父单号时,Cleaner 也能把子表清干净:
  - 父查目标 {table,key,parent:{table,key_col,marker_col}}
      → DELETE 子表 WHERE key IN (SELECT key_col FROM 父表 WHERE marker_col LIKE %marker%)
  - 直删目标 {table,column} 照旧按 marker 删父表。
  - 子表在前、父表在后:删子表时父行还在,子查询能命中。
  - 无关单据(别的父单号)不受影响。清理成功 registry 销账。

跑:python tests/test_cleaner_child.py
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

from core.cleaner import Cleaner  # noqa: E402
from core.interfaces import Expected, TestCase  # noqa: E402
from db.client import DbClient  # noqa: E402


def _setup(db_path: str) -> None:
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY, code TEXT, title TEXT)"))
        c.execute(text("CREATE TABLE child (id INTEGER PRIMARY KEY, code TEXT, note TEXT)"))
        # 本次造数:父单 C1,标题带 marker;两条子行挂 C1(子行不含 marker)
        c.execute(text("INSERT INTO parent (code,title) VALUES ('C1','AUTOTEST_X 新建')"))
        c.execute(text("INSERT INTO child (code,note) VALUES ('C1','行1'),('C1','行2')"))
        # 无关单据:父单 C2 与其子行,不该被动
        c.execute(text("INSERT INTO parent (code,title) VALUES ('C2','别人的单子')"))
        c.execute(text("INSERT INTO child (code,note) VALUES ('C2','无关')"))
    eng.dispose()


def _count(db: DbClient, sql: str) -> int:
    return db.query(sql)[0]["c"]


def main():
    d = tempfile.mkdtemp()
    db_path = os.path.join(d, "app.db").replace("\\", "/")
    reg = os.path.join(d, "registry.json")
    _setup(db_path)

    print("通用 Cleaner 子表按父单号清理 验证:\n")
    db = DbClient(dsn_readonly=f"sqlite:///{db_path}", dsn_write=f"sqlite:///{db_path}")
    marker = "AUTOTEST_X"
    case = TestCase(
        case_id="TCC01", feature="需求创建", account_ref="", data_prep=None,
        steps=[], expected=Expected(allowed_tables=["child", "parent"]),
        raw={"cleanup_targets": [
            # 子表在前:按父单号删(标记只在父表 title)
            {"table": "child", "key": "code",
             "parent": {"table": "parent", "key_col": "code", "marker_col": "title"}},
            # 父表在后:直接按 marker 删
            {"table": "parent", "column": "title"},
        ]},
    )

    cleaner = Cleaner(db, reg)
    cleaner.register(case, marker)
    ok = cleaner.cleanup(marker)

    assert ok, "清理应成功销账"
    assert _count(db, "SELECT COUNT(*) c FROM parent WHERE title LIKE '%AUTOTEST_X%'") == 0, "本次父单应删净"
    assert _count(db, "SELECT COUNT(*) c FROM child WHERE code='C1'") == 0, "本次子行应按父单号删净"
    print("    ✓ 子表只有父单号也能清:按父表标题标记反查父单号删子表")
    assert _count(db, "SELECT COUNT(*) c FROM parent WHERE code='C2'") == 1, "无关父单不该被动"
    assert _count(db, "SELECT COUNT(*) c FROM child WHERE code='C2'") == 1, "无关子行不该被动"
    print("    ✓ 无关单据(别的父单号)不受影响")
    assert not os.path.exists(reg) or marker not in open(reg, encoding="utf-8").read(), "成功清理应销账"
    print("    ✓ 清理成功 registry 销账")

    db.close()
    print("\n全部通过 ✅  —— 通用子表按父单号清理就位(标记只在父单也能连带清子表)")


if __name__ == "__main__":
    main()
