"""case-gen YAML converts to canonical cases while preserving traceability and draft state."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.import_casegen import convert_case  # noqa: E402


def main() -> None:
    item = {"id": "TC-001", "title": "列表展示", "priority": "P0", "level": "e2e",
            "type": "happy_path", "traceability": {"requirements": ["REQ-1"]},
            "preconditions": ["存在数据"], "steps": [{"action": "打开列表"}],
            "expected": [{"assertion": "显示条目", "observable": "ui"}], "status": "ready"}
    case = convert_case(item, "suite-x", "cases.yaml", 1)
    assert case["suite_id"] == "suite-x" and case["status"] == "draft"
    assert case["source"]["traceability"]["requirements"] == ["REQ-1"]
    assert case["layers"]["required"] == ["ui"]
    print("case-gen import passed")


if __name__ == "__main__":
    main()
