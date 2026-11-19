"""Manage captured asset candidates without bypassing review states."""
from __future__ import annotations

import argparse
import json

from core.asset_store import AssetStore
from core.asset_review import accept_replay_verified, review_queue
from core.exploration_promotion import apply_exploration_asset
from core.workspace import kb_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="资产候选治理")
    sub = parser.add_subparsers(dest="command", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--state")
    promote = sub.add_parser("promote")
    promote.add_argument("asset_id")
    promote.add_argument("state")
    promote.add_argument("--evidence", action="append", default=[])
    review = sub.add_parser("review-queue")
    accept = sub.add_parser("accept-replay")
    accept.add_argument("asset_id")
    accept.add_argument("--reviewer", required=True)
    accept.add_argument("--evidence", action="append", default=[])
    retire = sub.add_parser("retire-drifted")
    retire.add_argument("--max-drift-rate", type=float, default=0.2)
    bind = sub.add_parser("bind-exploration")
    bind.add_argument("asset_id")
    bind.add_argument("--suite", required=True)
    bind.add_argument("--workspace", default="workspace")
    bind.add_argument("--proof-ref", required=True,
                      choices=["ui.extract", "ui.visibility_asserts", "ui.value_asserts", "ui.field_asserts"])
    args = parser.parse_args()
    store = AssetStore(kb_dir() / "asset_candidates")
    if args.command == "list":
        print(json.dumps(store.list(state=args.state), ensure_ascii=False, indent=2))
        return 0
    if args.command == "retire-drifted":
        print(json.dumps({"retired": store.retire_drifted(max_drift_rate=args.max_drift_rate)},
                         ensure_ascii=False, indent=2))
        return 0
    if args.command == "review-queue":
        print(json.dumps(review_queue(store), ensure_ascii=False, indent=2))
        return 0
    if args.command == "accept-replay":
        print(json.dumps(accept_replay_verified(store, args.asset_id, reviewer=args.reviewer,
                                                evidence=args.evidence), ensure_ascii=False, indent=2))
        return 0
    if args.command == "bind-exploration":
        print(json.dumps(apply_exploration_asset(
            args.asset_id, workspace=args.workspace, suite=args.suite, proof_ref=args.proof_ref
        ), ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(store.promote(args.asset_id, args.state, evidence=args.evidence), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
