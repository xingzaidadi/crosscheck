"""
验证两个来自真实接口的改动:
  1. QueryMapper 跳过"不筛选"哨兵值(-1 / 空数组),不把它们拼进 WHERE。
  2. Reconciler 支持无分组的总数核对(data.total vs COUNT(DISTINCT pk))。

真实接口的列表请求体常是这个形状:大量 -1 + 空数组表示"该维度不筛选"。

跑:python tests/test_sentinel_total.py
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

from core.query_mapper import QueryMapper  # noqa: E402
from core.reconciler import Reconciler  # noqa: E402
from db.client import DbClient  # noqa: E402

# 贴近真实列表接口:categoryId 实际筛选,其余全是 -1/空=不筛选
MAPPING = {
    "feature": "列表检索", "db": "app_test", "table": "items", "pk": "item_id",
    "fixed_where": "tenant_id = 1 AND delete_status = 0",
    "param_map": {
        "searchKey": {"column": "item_name", "op": "like", "wrap": "%{v}%"},
        "categoryId": {"column": "category_id", "op": "eq"},
        "ownerTeamId": {"column": "owner_team_id", "op": "eq"},
        "createUserId": {"column": "create_user_id", "op": "eq"},
        "regionCodes": {"column": "register_region", "op": "in"},
    },
    "total_check": {"response_path": "data.total"},
    "field_sample_check": {"sample_size": 5,
                           "compare_fields": ["item_name", "category_id"]},
}

REAL_PARAMS = {
    "pageNo": 1, "pageSize": 20, "searchKey": "", "tagCode": "T1",
    "ownerTeamId": -1, "createUserId": -1, "provinceCode": -1,
    "regionCodes": [], "categoryId": 60,
}

ROWS = [
    # item_id, item_name, category_id, owner_team_id, create_user_id, register_region, tenant_id, delete_status
    (1, "物料A", 60, 5, 100, 1, 1, 0),
    (2, "物料B", 60, 7, 101, 1, 1, 0),
    (3, "物料C", 60, 9, 102, 2, 1, 0),
    (4, "物料D", 20, 5, 100, 1, 1, 0),   # category_id=20,应被滤掉
    (5, "物料E", 60, 5, 100, 1, 1, 1),   # delete_status=1,应被滤掉
]


def setup(path):
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE items (item_id INTEGER PRIMARY KEY, item_name TEXT,"
                       " category_id INT, owner_team_id INT, create_user_id INT,"
                       " register_region INT, tenant_id INT, delete_status INT)"))
        for r in ROWS:
            c.execute(text("INSERT INTO items VALUES (:a,:b,:c,:d,:e,:f,:g,:h)"),
                      dict(zip("abcdefgh", r)))
    eng.dispose()
    return DbClient(dsn_readonly=f"sqlite:///{path}")


def test_sentinel_skipped():
    w = QueryMapper(MAPPING).build_where(REAL_PARAMS)
    # -1 和空数组不该出现在 WHERE;只有 category_id=60 该进去
    assert "owner_team_id" not in w.sql, w.sql
    assert "create_user_id" not in w.sql, w.sql
    assert "register_region" not in w.sql, w.sql   # regionCodes=[] 跳过
    assert "category_id = :" in w.sql, w.sql
    assert 60 in w.params.values()
    assert -1 not in w.params.values()
    print("  ✓ 哨兵值(-1/空数组)被正确跳过,只有真实筛选条件进 WHERE")


def test_total_consistent(db):
    # category_id=60 且过 fixed_where → id 1,2,3 共 3 条
    resp = {"data": {"total": 3, "list": [
        {"item_id": 1, "item_name": "物料A", "category_id": 60},
        {"item_id": 2, "item_name": "物料B", "category_id": 60},
    ]}}
    res = db_reconcile(db, resp)
    assert res.consistent, res.render()
    print("  ✓ 总数核对一致: 接口 total=3 == 库 COUNT(DISTINCT)=3")


def test_total_inconsistent(db):
    resp = {"data": {"total": 99, "list": [
        {"item_id": 1, "item_name": "物料A", "category_id": 60},
    ]}}
    res = db_reconcile(db, resp)
    assert not res.consistent
    assert any("总数" in d for d in res.count_diffs), res.render()
    print("  ✓ 总数核对不一致: 抓到 接口=99 vs 库=3")
    print("    报告:", res.count_diffs[0])


def db_reconcile(db, resp):
    return Reconciler(db, MAPPING).reconcile(REAL_PARAMS, resp)


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = setup(os.path.join(d, "t.db"))
        try:
            print("真实接口形状验证(哨兵跳过 + 总数核对):")
            test_sentinel_skipped()
            test_total_consistent(db)
            test_total_inconsistent(db)
        finally:
            db.close()
    print("\n全部通过 ✅")


if __name__ == "__main__":
    main()
