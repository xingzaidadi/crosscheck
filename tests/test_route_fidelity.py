"""Reused case IDs must not bind stale routes or verified specs."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.modeler import _norm_title, route_case  # noqa: E402


def main() -> None:
    routes = {
        "defaults": {"db": "demo"},
        "by_case_id": {
            "TC03": {"case_title": "TC03-字段联动-当前操作人", "feature": "旧功能"},
        },
        "by_keyword": [{"match": ["页签计算"], "feature": "新功能"}],
    }
    stale = SimpleNamespace(case_id="TC03", name="TC03-页签计算-待下单", steps_text="", module="")
    matched, source = route_case(stale, routes)
    assert matched and matched["feature"] == "新功能", matched
    assert source == "keyword"
    old = SimpleNamespace(case_id="TC03", name="TC03-字段联动-当前操作人", steps_text="", module="")
    matched, source = route_case(old, routes)
    assert matched["feature"] == "旧功能" and source == "case_id"
    assert _norm_title("TC03-标题 A") == _norm_title("标题A")
    print("route fidelity passed")


if __name__ == "__main__":
    main()
