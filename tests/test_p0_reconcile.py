"""
对账链的可运行验证(sqlite fixture,不碰真实库)。

验证三件事:
  1. QueryMapper 把接口参数确定性翻译成 WHERE(含枚举翻译、绑定参数防注入)。
  2. Reconciler 在"接口与库一致"时判 consistent。
  3. Reconciler 在"不一致"时判 inconsistent,并指出差在哪组/哪条/哪字段。

跑:python tests/test_p0_reconcile.py
"""
from __future__ import annotations

import os
import sys
import tempfile

# Windows 控制台默认 GBK,强制 stdout 走 utf-8 才能打出 ✓ 和中文
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402

from core.query_mapper import QueryMapper  # noqa: E402
from core.reconciler import Reconciler  # noqa: E402
from db.client import DbClient  # noqa: E402


# query_mapping(sqlite 版:去掉 like 的 % 便于精确断言,保留结构)
MAPPING = {
    "feature": "列表检索", "db": "app_test", "table": "items", "pk": "id",
    "fixed_where": "tenant_id = 1 AND delete_status = 0",
    "param_map": {
        "name": {"column": "name", "op": "like", "wrap": "%{v}%"},
        "region": {"column": "region", "op": "eq",
                   "enum_translation": {"华北": 1, "华南": 2}},
        "status": {"column": "status", "op": "in"},
    },
    "group_by": {
        "response_path": "data.statusGroups",
        "group_key_field": "status", "group_count_field": "count",
        "sql_group_column": "status",
    },
    "field_sample_check": {
        "sample_size": 5,
        "compare_fields": ["name", "category_id", "status", "region"],
    },
}

FIXTURE_ROWS = [
    # id, name, category_id, status, region, tenant_id, delete_status
    (1, "AUTOTEST_甲", 20, "draft",  1, 1, 0),
    (2, "AUTOTEST_乙", 20, "draft",  1, 1, 0),
    (3, "AUTOTEST_丙", 10, "active", 1, 1, 0),
    (4, "AUTOTEST_丁", 20, "active", 2, 1, 0),
    (5, "AUTOTEST_戊", 20, "draft",  1, 1, 1),   # delete_status=1,应被 fixed_where 排除
    (6, "别人家的",     20, "draft",  1, 2, 0),   # 别的租户,应被排除
]


# items-tag 关联表(模拟真实的多对多维度表):
# 决定"命中某标签"的列表过滤就落在这里,主表 WHERE 表达不了,必须 join。
# id 4 只关联 T2,未关联 T1 → 应被 tag_code='T1' 过滤掉。
ITEM_TAG_ROWS = [
    # item_id, tag_code
    (1, "T1"), (1, "T2"),
    (2, "T1"),
    (3, "T1"),
    (4, "T2"),          # 只在 T2,T1 列表里看不到它
]


def setup_db(path: str) -> DbClient:
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as c:
        c.execute(text(
            "CREATE TABLE items ("
            "id INTEGER PRIMARY KEY, name TEXT, code TEXT, category_id INT, "
            "status TEXT, region INT, register_region INT, tenant_id INT, delete_status INT)"
        ))
        for r in FIXTURE_ROWS:
            c.execute(text(
                "INSERT INTO items "
                "(id,name,category_id,status,region,tenant_id,delete_status) "
                "VALUES (:id,:name,:ct,:st,:rg,:tid,:ds)"
            ), {"id": r[0], "name": r[1], "ct": r[2], "st": r[3],
                "rg": r[4], "tid": r[5], "ds": r[6]})
        c.execute(text(
            "CREATE TABLE item_tags ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INT, tag_code TEXT)"
        ))
        for iid, tag in ITEM_TAG_ROWS:
            c.execute(text(
                "INSERT INTO item_tags (item_id,tag_code) "
                "VALUES (:i,:t)"), {"i": iid, "t": tag})
    eng.dispose()   # 释放建表用的引擎,别占着文件句柄
    return DbClient(dsn_readonly=f"sqlite:///{path}")


def test_query_mapper():
    m = QueryMapper(MAPPING)
    w = m.build_where({"name": "AUTOTEST", "region": "华北", "status": ["draft", "active"]})
    # 固定条件在、枚举 华北→1、status IN、值全部走绑定参数
    assert "tenant_id = 1" in w.sql
    assert "LIKE" in w.sql and "region = :" in w.sql and "status IN (" in w.sql
    assert 1 in w.params.values()                      # 华北已翻译成 1
    assert any("%AUTOTEST%" == v for v in w.params.values())
    assert m.unknown_params({"name": "x", "weird": "y"}) == ["weird"]
    print("  ✓ QueryMapper: 参数→WHERE / 枚举翻译 / 绑定参数 / 未知参数检出")


def test_reconcile_consistent(db: DbClient):
    r = Reconciler(db, MAPPING)
    # 真实库(经 fixed_where 过滤后): draft=2(id1,2), active=2(id3,4)
    api_resp = {
        "data": {
            "statusGroups": [
                {"status": "draft", "count": 2},
                {"status": "active", "count": 2},
            ],
            "list": [
                {"id": 1, "name": "AUTOTEST_甲", "category_id": 20, "status": "draft", "region": 1},
                {"id": 4, "name": "AUTOTEST_丁", "category_id": 20, "status": "active", "region": 2},
            ],
        }
    }
    res = r.reconcile({"name": "AUTOTEST"}, api_resp)
    assert res.consistent, res.render()
    assert res.checked_groups == 2 and res.checked_rows == 2
    print("  ✓ Reconcile 一致场景: 分组数量 + 字段抽样全对上")


def test_reconcile_inconsistent(db: DbClient):
    r = Reconciler(db, MAPPING)
    api_resp = {
        "data": {
            "statusGroups": [
                {"status": "draft", "count": 3},     # 接口多报 1(库只有 2)
                {"status": "active", "count": 2},
            ],
            "list": [
                {"id": 1, "name": "AUTOTEST_甲", "category_id": 20, "status": "draft", "region": 1},
                {"id": 3, "name": "名字对不上", "category_id": 10, "status": "active", "region": 1},
            ],
        }
    }
    res = r.reconcile({"name": "AUTOTEST"}, api_resp)
    assert not res.consistent
    assert any("draft" in d for d in res.count_diffs), res.render()
    assert any("name" in d and "pk=3" in d for d in res.field_diffs), res.render()
    print("  ✓ Reconcile 不一致场景: 抓到数量差(draft) + 字段差(pk=3 name)")
    print("    ↓ 报告样例:")
    for line in res.render().splitlines():
        print("      " + line)


# join + response_field_map 场景:多对多维度过滤在关联表 + 接口 camelCase 字段
JOIN_MAPPING = {
    "feature": "列表检索", "db": "app_test",
    "table": "items", "table_alias": "v", "pk": "id",
    "fixed_where": "v.delete_status = 0 AND v.tenant_id = 1",
    "joins": [{
        "type": "JOIN", "table": "item_tags", "alias": "t",
        "on": "t.item_id = v.id",
    }],
    "param_map": {
        "searchKey": {"column": "v.name", "op": "like", "wrap": "%{v}%"},
        "categoryId": {"column": "v.category_id", "op": "eq"},
        "tagCode": {"column": "t.tag_code", "op": "eq"},
    },
    "total_check": {"response_path": "data.total"},
    "response_field_map": {
        "id": "itemId", "name": "itemName", "category_id": "categoryId",
    },
    "field_sample_check": {"sample_size": 5, "compare_fields": ["name", "category_id"]},
}


def test_reconcile_join_and_fieldmap(db: DbClient):
    # 接口参数:category=20、标签 T1。真实库经 fixed_where + join 过滤后应得 id1,id2(共 2):
    #   id1(T1+T2,join 需 DISTINCT 去重)、id2(T1);id4 只在 T2 被排除;id5 ds=1;id6 别租户。
    r = Reconciler(db, JOIN_MAPPING)
    api_resp = {
        "data": {
            "total": 2,
            "records": [
                {"itemId": 1, "itemName": "AUTOTEST_甲", "categoryId": 20},
                {"itemId": 2, "itemName": "AUTOTEST_乙", "categoryId": 20},
            ],
        }
    }
    res = r.reconcile({"categoryId": 20, "tagCode": "T1"}, api_resp)
    assert res.consistent, res.render()
    assert res.checked_rows == 2
    print("  ✓ join + camelCase 字段映射: 标签过滤(关联表)+ itemId/itemName 翻译后对上, total=2")

    # 反证:去掉 join,同样条件会把只在 T2 的 id4 也算进来 → 库=3 ≠ 接口 2 → 不一致。
    no_join = {k: v for k, v in JOIN_MAPPING.items() if k != "joins"}
    no_join = {**no_join, "fixed_where": "delete_status = 0 AND tenant_id = 1",
               "table_alias": "", "param_map": {
                   "categoryId": {"column": "category_id", "op": "eq"},
                   "tagCode": {"column": "_SKIP_", "op": "eq"}}}
    res2 = Reconciler(db, no_join).reconcile({"categoryId": 20, "tagCode": "T1"}, api_resp)
    assert not res2.consistent and any("总数" in d for d in res2.count_diffs), res2.render()
    print("  ✓ 反证: 不 join 标签则多算 id4(库=3 vs 接口=2),证明 join 过滤是必需的")


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = setup_db(os.path.join(d, "t.db"))
        try:
            print("对账链验证:")
            test_query_mapper()
            test_reconcile_consistent(db)
            test_reconcile_inconsistent(db)
            test_reconcile_join_and_fieldmap(db)
        finally:
            db.close()   # 释放 sqlite 文件句柄,否则 Windows 下临时目录清理失败
    print("\n全部通过 ✅")


if __name__ == "__main__":
    main()
