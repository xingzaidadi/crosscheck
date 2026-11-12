"""Suite planning: fingerprints and UI/API/DB coverage gaps."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.suite_plan import build_suite_plan, suite_fingerprint  # noqa: E402


def raw(case_id, name, steps, expected):
    return SimpleNamespace(case_id=case_id, name=name, module="模块/子模块", category="模块/子模块",
                           tags="", preconditions="", notes="", steps_text=steps,
                           expected_text=expected, level="P0")


def main() -> None:
    cases = [raw("TC01", "TC01-列表一致性", "打开页面并调用 POST /api/list，查库", "页面、接口、数据库一致")]
    spec = SimpleNamespace(case_id="TC01", mode="reconcile", ui={}, request={"url": "/api/list"},
                           assertions={"db": [{"table": "items"}]}, verify_status="human_verified",
                           blocked="", needs_review=[])
    plan = build_suite_plan(cases, [spec], "cases.xlsx")
    assert plan["three_layer_required"] == 1
    assert plan["three_layer_ready"] == 0
    assert plan["cases"][0]["missing_layers"] == ["ui"]
    ui_spec = SimpleNamespace(case_id="TC01", mode="ui", ui={"url_pattern": "/api/list"}, request={},
                              assertions={}, db="demo", feature="列表", verify_status="human_verified",
                              blocked="", needs_review=[])
    ui_plan = build_suite_plan(cases, [ui_spec], "cases.xlsx")
    assert ui_plan["three_layer_ready"] == 1
    assert ui_plan["cases"][0]["provided_layers"] == ["ui", "api", "db"]
    changed = [raw("TC01", "TC01-不同语义", "调用接口", "成功")]
    assert suite_fingerprint(cases) != suite_fingerprint(changed)
    print("suite plan passed")


if __name__ == "__main__":
    main()
