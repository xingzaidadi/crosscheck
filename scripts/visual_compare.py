"""Compare a visual baseline and actual screenshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.visual_gate import compare


def main() -> int:
    parser = argparse.ArgumentParser(description="比较截图 baseline 与 actual")
    parser.add_argument("reference", type=Path)
    parser.add_argument("actual", type=Path)
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--mask", action="append", default=[], help="left,top,right,bottom")
    args = parser.parse_args()
    masks = []
    for value in args.mask:
        parts = [int(item.strip()) for item in value.split(",")]
        if len(parts) != 4:
            raise SystemExit("--mask must be left,top,right,bottom")
        masks.append(tuple(parts))
    result = compare(args.reference, args.actual, threshold=args.threshold, mask=masks)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
