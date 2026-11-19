"""The bundled demo proves browser, HTTP API, database assertion and cleanup."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.local_demo import run_demo  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        result = run_demo(Path(directory))
        assert result["passed"]
        assert result["api"]["status"] == 201
        assert result["db"]["residue"] == 0
    print("local demo passed")


if __name__ == "__main__":
    main()
