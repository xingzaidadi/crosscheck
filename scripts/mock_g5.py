"""Run local requirement→strategy→delivery G5 acceptance."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from core.g5 import run_g5


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="crosscheck-g5-") as directory:
        result = run_g5(directory)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
