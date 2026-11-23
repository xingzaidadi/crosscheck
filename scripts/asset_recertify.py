"""Request, submit, or approve approved-asset recertification."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.asset_recertification import (  # noqa: E402
    approve_recertification, request_recertification, submit_recertification_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="重新认证 degraded/unhealthy Fixture 或 Oracle")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--asset-type", choices=("fixture", "oracle"), required=True)
    parser.add_argument("--asset-id", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    request = sub.add_parser("request")
    request.add_argument("--requester", required=True)
    request.add_argument("--reason", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("--submitter", required=True)
    submit.add_argument("--soak-runs", type=int, required=True)
    submit.add_argument("--passed-runs", type=int, required=True)
    submit.add_argument("--evidence", action="append", required=True)
    approve = sub.add_parser("approve")
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--minimum-soak-runs", type=int, default=5)
    args = parser.parse_args()
    if args.action == "request":
        result = request_recertification(args.suite, args.asset_type, args.asset_id,
                                         requester=args.requester, reason=args.reason)
    elif args.action == "submit":
        result = submit_recertification_evidence(args.suite, args.asset_type, args.asset_id,
                                                 submitter=args.submitter, soak_runs=args.soak_runs,
                                                 passed_runs=args.passed_runs, evidence=args.evidence)
    else:
        result = approve_recertification(args.suite, args.asset_type, args.asset_id,
                                         reviewer=args.reviewer, minimum_soak_runs=args.minimum_soak_runs)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
