"""Canonical importer creates isolated suites with globally unique IDs."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.import_suite import canonical_case, slug  # noqa: E402


def main() -> None:
    raw = SimpleNamespace(case_id="TC01", name="TC01-列表查询", row=2, level="P0",
                          module="模块/列表", category="模块/列表", tags="", preconditions="有数据",
                          notes="", steps_text="打开页面调用 /x/api/list", expected_text="页面接口一致")
    case = canonical_case(raw, "suite-a", "cases.xlsx")
    assert case["case_id"].startswith("suite-a/")
    assert case["source"]["case_key"] == "TC01"
    assert case["status"] == "draft"
    assert slug("TC01-列表查询") == "列表查询"
    print("suite import passed")


if __name__ == "__main__":
    main()
