"""core.mapping_builder 真执行回归(main()+assert)。

mapping_builder 是"抓包样本 → query_mapping 草稿"的自动建模核心(参数→库列、
op 推断、分组计数/总数检测、返回行字段映射),此前覆盖仅 9%。本文件以 main()+assert
在 run_tests.py 下真执行,锁住各确定性推断分支,避免纯 fixture 风格的假通过。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.mapping_builder import (
    build_mapping_draft,
    camel_to_snake,
    _match_column,
    _flatten_params,
    _detect_group_by,
    _detect_rows,
    _detect_total,
)
from core.prober import Capture


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _cap(url="https://x/api/list", method="POST", query=None, body=None, resp=None):
    return Capture(
        url=url,
        method=method,
        resource_type="xhr",
        request_body=body,
        query_params=query or {},
        status=200,
        response_json=resp,
        ts=0.0,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # 1) camel_to_snake 归一化。
    _assert(camel_to_snake("classificationType") == "classification_type", "camel→snake 基本")
    _assert(camel_to_snake("itemID") == "item_id", "尾部连续大写")
    _assert(camel_to_snake("already_snake") == "already_snake", "已是 snake 不变")
    print("[1] camel_to_snake 归一化 ✓")

    # 2) _match_column 三级匹配:原名 / snake 化 / 去下划线。
    cols = ["classification_type", "item_name", "orderno"]
    _assert(_match_column("classificationType", cols) == "classification_type", "snake 化命中")
    _assert(_match_column("item_name", cols) == "item_name", "原名命中")
    _assert(_match_column("orderNo", cols) == "orderno", "去下划线命中")
    _assert(_match_column("nonexist", cols) is None, "匹配不上返回 None")
    print("[2] _match_column 三级匹配 ✓")

    # 3) _flatten_params:合并 query 与 body 顶层,跳过分页参数。
    cap = _cap(query={"status": "A"}, body={"name": "x", "page": 2, "pageSize": 20, "offset": 0})
    flat = _flatten_params(cap)
    _assert(flat == {"status": "A", "name": "x"}, f"分页参数应被跳过, got {flat}")
    print("[3] _flatten_params 跳过分页 ✓")

    # 4) _detect_group_by:识别 [{<key>:x, count:n}] 分组计数。
    resp_group = {"data": {"statusGroups": [{"statusCode": "DRAFT", "count": 3},
                                            {"statusCode": "DONE", "count": 5}]}}
    gb = _detect_group_by(resp_group)
    _assert(gb is not None, "应检出分组")
    _assert(gb["response_path"] == "data.statusGroups", "分组 response_path")
    _assert(gb["group_count_field"] == "count", "计数字段")
    _assert(gb["group_key_field"] == "statusCode", "分组键字段")
    _assert(gb["sql_group_column"] == "status_code", "分组列 snake 化")
    _assert(_detect_group_by({"data": {}}) is None, "无分组结构返回 None")
    _assert(_detect_group_by("notdict") is None, "非 dict 返回 None")
    print("[4] _detect_group_by 分组计数检测 ✓")

    # 5) _detect_rows:list/rows/records 三种路径 + 顶层 list。
    _assert(_detect_rows({"data": {"list": [{"a": 1}]}}) == [{"a": 1}], "data.list")
    _assert(_detect_rows({"data": {"rows": [{"b": 2}]}}) == [{"b": 2}], "data.rows")
    _assert(_detect_rows({"data": [{"c": 3}]}) == [{"c": 3}], "data 顶层 list")
    _assert(_detect_rows({"data": {}}) == [], "无行返回空")
    print("[5] _detect_rows 结果列表路径 ✓")

    # 6) _detect_total:无分组时找总数字段。
    tot = _detect_total({"data": {"total": 42}})
    _assert(tot is not None and tot["response_path"] == "data.total", "检出 data.total")
    _assert(_detect_total({"data": {"totalCount": 7}})["response_path"] == "data.totalCount", "totalCount")
    _assert(_detect_total({"data": {}}) is None, "无总数返回 None")
    print("[6] _detect_total 总数检测 ✓")

    # 7) build_mapping_draft 端到端:op 推断 + 未匹配列进 _needs_review + 字段映射。
    cap2 = _cap(
        body={"statusList": ["A", "B"], "keyword": "abc", "ghostParam": "z"},
        resp={"data": {"list": [{"classificationType": "T", "itemName": "n", "itemId": 9}],
                       "total": 1}},
    )
    draft = build_mapping_draft(
        cap2, db_name="shop", table="v_item", pk="id",
        columns=["status_list", "keyword", "classification_type"],
    )
    pm = draft["param_map"]
    _assert(pm["statusList"]["op"] == "in", "list 值 → op=in")
    _assert(pm["statusList"]["column"] == "status_list", "statusList 匹配列")
    _assert(pm["keyword"]["op"] == "like" and pm["keyword"]["wrap"] == "%{v}%", "str 值 → like + wrap")
    _assert(pm["ghostParam"]["column"].startswith("TODO_"), "未匹配参数列标 TODO_")
    _assert("_needs_review" in pm["ghostParam"], "未匹配参数带 _needs_review")
    _assert(any("ghostParam" in n for n in draft["_review_notes"]), "未匹配参数进 review_notes")
    # 返回字段映射:classificationType 语法匹配上 classification_type。
    _assert("classification_type" in draft["field_sample_check"]["compare_fields"], "命中字段进 compare")
    _assert(draft["response_field_map"].get("classification_type") == "classificationType",
            "列≠接口字段名 → 进 response_field_map")
    _assert(draft["total_check"] is not None, "无分组时产 total_check")
    _assert(draft["verify_status"] == "auto_discovered_pending", "草稿待人审状态")
    print("[7] build_mapping_draft 端到端(op/未匹配/字段映射/total) ✓")

    # 8) 有分组时 total_check 让位给 group_by。
    cap3 = _cap(body={"k": "v"},
                resp={"data": {"g": [{"name": "x", "count": 1}], "total": 99}})
    draft3 = build_mapping_draft(cap3, "d", "t", "id", ["k"])
    _assert(draft3["group_by"] is not None, "检出分组")
    _assert(draft3["total_check"] is None, "有分组时 total_check 让位")
    print("[8] 分组优先于 total_check ✓")

    print("\nALL PASS · core.mapping_builder 自动建模推断(camel/match/flatten/group/rows/total/draft)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
