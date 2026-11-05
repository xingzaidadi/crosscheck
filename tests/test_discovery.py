"""
自发现 + 自进化 核心验证(离线,sqlite + 临时 workspace,无浏览器)。
  1. db_intel.table_constraints:从 schema 判出必填列(NOT NULL 且无默认非自增)+ 样例值;
  2. FieldIntel 知识库:merge 新发现 → known;record 失效累计 → stale;存盘→重载仍在(跨次进化);
     高权重出处(docs)可覆盖低权重(frontend)的值提示。

跑:python tests/test_discovery.py
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

from core.workspace import set_workspace  # noqa: E402
from core.discovery.db_intel import table_constraints, sample_values  # noqa: E402
from core.discovery.knowledge import FieldIntel  # noqa: E402
from db.client import DbClient  # noqa: E402


def _db(path):
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', note TEXT)"))
        for n in ("甲", "乙", "甲"):
            c.execute(text("INSERT INTO items (name,status) VALUES (:n,'active')"), {"n": n})
    eng.dispose()
    return DbClient(dsn_readonly=f"sqlite:///{path}")


def main():
    print("自发现 + 自进化 核心验证:\n")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        set_workspace(d)
        db = _db(os.path.join(d, "t.db"))
        try:
            # 1) 库约束探针
            cons = table_constraints(db, "items")
            assert cons["name"]["required"] is True, cons["name"]
            assert cons["status"]["required"] is False     # 有默认值
            assert cons["note"]["required"] is False        # 可空
            assert cons["id"]["required"] is False          # 自增主键
            print("    ✓ 库约束: 判出必填列=name(NOT NULL 无默认非自增),status/note/id 非必填")
            sv = sample_values(db, "items", ["name"])
            assert "甲" in sv["name"], sv
            print("    ✓ 样例值: name 常见取值", sv["name"])
        finally:
            db.close()

        # 2) 知识库 merge + known + required
        ki = FieldIntel("列表检索")
        ki.merge([{"label": "名称", "selector": "#name", "control": "text", "required": True},
                  {"label": "状态", "selector": "#status", "control": "select", "options": ["active", "draft"]}],
                 source="frontend")
        ki.merge([{"key": "名称", "value_hint": "甲"}], source="db")  # 库补样例值
        assert ki.known() and "名称" in ki.required_fields()
        assert ki.fields["名称"]["value_hint"] == "甲"
        print("    ✓ 知识库: 前端发现必填『名称』+ 库补样例值『甲』,已知可秒填")

        # 3) 失效累计 → stale(页面变了会重探)
        for _ in range(3):
            ki.record("名称", ok=False)
        assert "名称" in ki.stale_fields()
        print("    ✓ 自愈: 『名称』连续失效 → 标记 stale(下次重探)")

        # 4) 存盘 → 重载仍在(跨次进化)
        p = ki.save()
        assert p.exists()
        ki2 = FieldIntel("列表检索")
        assert ki2.known() and "名称" in ki2.fields
        print(f"    ✓ 进化持久化: 存 {p.name} 重载仍在 —— 下次运行直接复用")

        # 5) 高权重出处覆盖(docs 覆盖 frontend 的值提示)
        ki2.merge([{"key": "名称", "value_hint": "PRD规定值"}], source="docs")
        assert ki2.fields["名称"]["value_hint"] == "PRD规定值"
        print("    ✓ 出处优先: 文档(业务口径)覆盖前端的值提示")

    print("\n全部通过 ✅  —— 通用自发现(库约束)+ 自进化知识库 核心就位")


if __name__ == "__main__":
    main()
