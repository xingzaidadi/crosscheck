"""db_exec 造态写库步骤 回归(离线、零环境、零业务词):
  - 参数化 SQL 的 {{var}} 以当前 vars 回填后执行
  - 多条 SQL 依次执行
  - 安全栏:UPDATE/DELETE 无 WHERE 被拒(不执行)
  - 失败计入 env_reasons(不崩)
用假 db 注入,毫秒级。跑:python tests/test_db_exec_prep.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import _run_prep_step  # noqa: E402


class FakeDB:
    def __init__(self, fail_on=None):
        self.writes = []
        self.fail_on = fail_on
    def query(self, sql, params=None):
        return [{"v": None}]
    def execute_write(self, sql, params=None):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("boom")
        self.writes.append(sql)
        return 1


def main():
    # ① {{var}} 回填 + 多条依次执行
    db = FakeDB()
    vars = {"id": 42, "marker": "AUTOTEST_X"}
    prep = {"db_exec": [
        "UPDATE widget SET state='DONE' WHERE id={{id}}",
        "INSERT INTO widget_node (widget_id, state) VALUES ({{id}}, 'EXECUTED')",
    ]}
    did, env = _run_prep_step(prep, adapter=None, db=db, vars=vars)
    assert env == [], env
    assert db.writes[0] == "UPDATE widget SET state='DONE' WHERE id=42", db.writes
    assert "VALUES (42," in db.writes[1], db.writes
    assert len(db.writes) == 2
    print("    ✓ {{var}} 回填 + 多条 SQL 依次执行")

    # ② 安全栏:UPDATE/DELETE 无 WHERE 被拒,不执行
    db2 = FakeDB()
    prep2 = {"db_exec": ["UPDATE widget SET state='X'", "DELETE FROM widget"]}
    did2, env2 = _run_prep_step(prep2, adapter=None, db=db2, vars={})
    assert db2.writes == [], db2.writes
    assert len(env2) == 2 and all("拒绝无 WHERE" in e for e in env2), env2
    print("    ✓ UPDATE/DELETE 无 WHERE 被拒(不写库,计 env)")

    # ③ INSERT 无 WHERE 允许(新增行天然无 WHERE)
    db3 = FakeDB()
    did3, env3 = _run_prep_step({"db_exec": "INSERT INTO widget_node (state) VALUES ('EXECUTED')"}, None, db3, {})
    assert db3.writes and env3 == [], (db3.writes, env3)
    print("    ✓ INSERT 无 WHERE 正常执行")

    # ④ 执行异常计入 env,不崩
    db4 = FakeDB(fail_on="widget_node")
    _, env4 = _run_prep_step({"db_exec": "INSERT INTO widget_node (state) VALUES ('X')"}, None, db4, {})
    assert env4 and "db_exec 失败" in env4[0], env4
    print("    ✓ 执行异常计入 env_reasons(不崩)")

    print("\ndb_exec 造态写库步骤 通过 ✅")


if __name__ == "__main__":
    main()
