"""Approve or reject one remediation draft with an explicit reviewer."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.remediation_review import review_draft  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="审核并晋级前置状态或业务 Oracle 草稿")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--decision", choices=("approve", "reject"), required=True)
    parser.add_argument("--updates", help="JSON object used to complete the draft before approval")
    parser.add_argument("--evidence", action="append", default=[])
    args = parser.parse_args()
    updates = json.loads(args.updates) if args.updates else None
    if updates is not None and not isinstance(updates, dict):
        raise ValueError("--updates must be a JSON object")
    result = review_draft(args.plan, args.suite, args.asset_id, reviewer=args.reviewer,
                          decision=args.decision, updates=updates, evidence=args.evidence)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
