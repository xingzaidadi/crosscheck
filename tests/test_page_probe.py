"""
表格结构探测 验证(离线、零业务):从多表页面自动选数据表 + 列映射 + 值相等绑接口字段。

跑:python tests/test_page_probe.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.discovery.page_probe import (  # noqa: E402
    pick_data_table, build_columns, match_dom_to_api, build_extract,
)


def main():
    print("表格结构探测 验证:\n")

    # 组件库典型:表头表(0行) + 表体表(3行) + 两张日历噪音表
    tables = [
        {"wrapper": "ui-table-header", "headers": ["", "编号", "名称", "状态"], "row0": [], "rows": 0},
        {"wrapper": "ui-table-body", "headers": ["", "编号", "名称", "状态"],
         "row0": ["", "A-100", "手机壳", "DONE"], "rows": 3},
        {"wrapper": "date-picker__calendar", "headers": [], "row0": ["1", "2", "3"], "rows": 6},
        {"wrapper": "date-picker__calendar", "headers": [], "row0": ["1", "2", "3"], "rows": 6},
    ]
    api_rows = [{"code": "A-100", "title": "手机壳", "st": "DONE", "qty": 1.0}]

    idx = pick_data_table(tables, api_len=1)
    assert idx == 1, idx
    print(f"    ✓ 4张表里选中表体表(idx={idx},排除表头表+日历噪音表)")

    cols = build_columns(tables[1]["headers"])
    assert cols == {"编号": "td:nth-child(2)", "名称": "td:nth-child(3)", "状态": "td:nth-child(4)"}, cols
    print(f"    ✓ 非空表头→nth-child(跳过前导复选框列): {cols}")

    d2a = match_dom_to_api(tables[1]["headers"], tables[1]["row0"], api_rows[0])
    assert d2a == {"编号": "code", "名称": "title", "状态": "st"}, d2a
    print(f"    ✓ 靠值相等绑定接口字段(不用中文字典): {d2a}")

    # 不传 body_wrapper_selector:rows_selector 自动从数据表 wrapper 推导(零硬编码)
    ex = build_extract(tables, api_rows, api_rows_path="data.list")
    assert ex["rows_selector"] == ".ui-table-body tbody tr", ex
    assert ex["_matched"] == 3 and ex["_columns_total"] == 3, ex
    print(f"    ✓ 汇总出 ui.extract(选择器自动推导): rows_selector={ex['rows_selector']} 匹配 {ex['_matched']}/{ex['_columns_total']} 列")

    # 数值归一:DOM '1' == 接口 1.0
    d2 = match_dom_to_api(["数量"], ["1"], {"qty": 1.0})
    assert d2 == {"数量": "qty"}, d2
    print("    ✓ 数值归一:DOM '1' 绑到接口 1.0")

    # 值冲突:两列同值,但只有一个接口字段是该值 → 只绑第一列,第二列留人审,不乱绑
    d3 = match_dom_to_api(["实际需求人", "提单人"], ["李四", "李四"],
                          {"demanderName": "李四", "applicantName": "王五"})
    assert d3 == {"实际需求人": "demanderName"}, d3
    print(f"    ✓ 两列同值仅一字段可绑:第二列留人审,不乱绑({d3})")

    # 组件库表头/表体分表:表头在 header 表,数据在 body 表,列按位置对齐
    split = [
        {"wrapper": "ui-table-header", "headers": ["", "编号", "名称"], "row0": [], "rows": 0},
        {"wrapper": "ui-table-body", "headers": [], "row0": ["", "A-1", "鼠标"], "rows": 2},
    ]
    ex2 = build_extract(split, [{"code": "A-1", "nm": "鼠标"}],
                        api_rows_path="data.list", body_wrapper_selector=".ui-table-body")
    assert ex2["columns"] == {"编号": "td:nth-child(2)", "名称": "td:nth-child(3)"}, ex2
    assert ex2["dom_to_api"] == {"编号": "code", "名称": "nm"}, ex2
    print("    ✓ 表头/表体分表:表头取 header 表、数据取 body 表,仍能出列+绑字段")

    print("\n全部通过 ✅  —— 表格结构探测就位:给页面自动产 UI 断言选择器,免手工扒")


if __name__ == "__main__":
    main()
