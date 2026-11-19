"""Record and inspect approved visual baselines."""
from __future__ import annotations

import argparse
import json

from core.visual_store import VisualBaselineStore
from core.visual_gate import compare
from core.workspace import artifacts_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="视觉 baseline 管理")
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record")
    record.add_argument("component")
    record.add_argument("image")
    record.add_argument("--approver", default="")
    get = sub.add_parser("get")
    get.add_argument("component")
    check = sub.add_parser("compare")
    check.add_argument("component")
    check.add_argument("actual")
    check.add_argument("--threshold", type=float, default=0.0)
    check.add_argument("--mask", action="append", default=[])
    args = parser.parse_args()
    store = VisualBaselineStore(artifacts_dir() / "visual-baselines")
    if args.command == "record":
        print(json.dumps(store.record(args.component, args.image, approver=args.approver), ensure_ascii=False, indent=2))
    elif args.command == "get":
        print(json.dumps(store.get(args.component), ensure_ascii=False, indent=2))
    else:
        baseline = store.get(args.component)
        masks = []
        for value in args.mask:
            parts = [int(item.strip()) for item in value.split(",")]
            if len(parts) != 4:
                raise SystemExit("--mask must be left,top,right,bottom")
            masks.append(tuple(parts))
        result = compare(baseline["path"], args.actual, threshold=args.threshold, mask=masks)
        result["component"] = args.component
        result["baseline_sha256"] = baseline["sha256"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
