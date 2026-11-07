"""
UI 规格自动装配 验证(离线、零业务):page_probe 产物 + case → 可跑三层 UI 规格。

跑:python tests/test_ui_autospec.py
"""
from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ui_autospec import assemble_ui_spec, spec_is_runnable  # noqa: E402


def main():
    print("UI 规格自动装配 验证:\n")
    case = {"case_id": "C-1", "title": "列表只读展示", "level": "P1", "category": "展示"}
    extract = {
        "rows_selector": ".x-table-body tbody tr",
        "columns": {"编号": "td:nth-child(2)", "名称": "td:nth-child(3)"},
        "dom_to_api": {"编号": "code", "名称": "name"},
        "api_rows_path": "data.records",
    }
    spec = assemble_ui_spec(case, feature="列表功能", page_url="https://h/list",
                            api_pattern="/api/list", extract=extract,
                            actions=[{"click": {"selector": "text=查询"}}],
                            session="s.json", base_url="https://h", db_name="d")
    assert spec["mode"] == "ui" and spec["verify_status"] == "human_verified", spec
    assert spec["ui"]["extract"]["rows_selector"] == ".x-table-body tbody tr", spec
    assert spec["ui"]["dom_to_api"] == {"编号": "code", "名称": "name"}, spec
    assert spec["ui"]["actions"] == [{"click": {"selector": "text=查询"}}], spec
    assert spec["feature"] == "列表功能", spec
    print("    ✓ 装配出 mode=ui 三层规格(页面+选择器+dom_to_api+feature映射+actions)")

    ok, why = spec_is_runnable(spec)
    assert ok, why
    print(f"    ✓ 自检可跑: {why}")

    # 一列都没绑到接口 → 判不了『显示==接口』,标不可跑待人审
    bad = assemble_ui_spec(case, feature="x", page_url="https://h/p", api_pattern="/api/p",
                           extract={"rows_selector": "table tbody tr", "columns": {"a": "td:nth-child(1)"}, "dom_to_api": {}})
    ok2, why2 = spec_is_runnable(bad)
    assert not ok2 and "dom_to_api" in why2, why2
    print(f"    ✓ 无字段绑定→判不可跑留人审: {why2}")

    print("\n全部通过 ✅  —— UI 规格自动装配就位:探测结果直接变可跑三层规格")


if __name__ == "__main__":
    main()
