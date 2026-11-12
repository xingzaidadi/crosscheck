"""Empty UI/API agreement is not sufficient unless the case explicitly allows empty state."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ui_verifier import verify_display  # noqa: E402


def main() -> None:
    response = {"data": {"records": []}}
    strict = verify_display([], response, {"api_rows_path": "data.records"})
    assert not strict.consistent and any("空集合" in diff for diff in strict.diffs)
    allowed = verify_display([], response, {"api_rows_path": "data.records", "allow_empty": True})
    assert allowed.consistent, allowed.diffs
    exact = verify_display([], response, {"api_rows_path": "data.records", "cardinality": {"exact_rows": 2}})
    assert not exact.consistent and any("预期 2" in diff for diff in exact.diffs)
    print("empty evidence gate passed")


if __name__ == "__main__":
    main()
