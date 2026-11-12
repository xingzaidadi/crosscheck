"""Security boundary regression tests."""
from __future__ import annotations

import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.security import trusted_workspace_script, validate_cleanup_targets


def main() -> None:
    validate_cleanup_targets(
        [{"table": "child", "key": "code", "parent": {
            "table": "parent", "key_col": "code", "marker_col": "title"}}],
        ["child", "parent"],
    )
    for targets, allowed in [
        ([{"table": "items; DROP TABLE users", "column": "name"}], ["items"]),
        ([{"table": "items", "column": "name"}], []),
    ]:
        try:
            validate_cleanup_targets(targets, allowed)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe cleanup target accepted")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        script = root / "check.py"
        script.write_text("print('ok')", encoding="utf-8")
        assert trusted_workspace_script("check.py", root) == script.resolve()
        try:
            trusted_workspace_script("../outside.py", root)
        except ValueError:
            pass
        else:
            raise AssertionError("workspace escape accepted")
    print("security boundary tests passed")


if __name__ == "__main__":
    main()
