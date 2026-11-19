"""DB metadata discovery is explicit for supported dialects and guarded otherwise."""
from __future__ import annotations

import os
import sys
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.client import DbClient  # noqa: E402


def main() -> None:
    db = object.__new__(DbClient)
    db._ro = Mock()
    db._ro.dialect.name = "oracle"
    try:
        db.tables()
    except RuntimeError as exc:
        assert "database plugin" in str(exc)
    else:
        raise AssertionError("unsupported dialect must not silently use MySQL metadata SQL")
    print("database dialect guard passed")


if __name__ == "__main__":
    main()
