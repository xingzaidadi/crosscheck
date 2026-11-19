"""Review, approve and activate UI binding assets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.asset_review import accept_replay_verified, activate_reviewed, review_queue
from core.asset_store import AssetStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["queue", "accept", "activate", "retire-drifted"])
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--asset-id")
    parser.add_argument("--reviewer")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--max-drift-rate", type=float, default=0.2)
    args = parser.parse_args()
    store = AssetStore(Path(args.workspace) / "knowledge_base" / "asset_candidates")
    if args.command == "queue":
        result = review_queue(store)
    elif args.command == "retire-drifted":
        result = {"retired": store.retire_drifted(max_drift_rate=args.max_drift_rate)}
    else:
        if not args.asset_id or not args.reviewer:
            parser.error("--asset-id and --reviewer are required")
        if args.command == "accept":
            result = accept_replay_verified(store, args.asset_id, reviewer=args.reviewer,
                                            evidence=args.evidence)
        else:
            result = activate_reviewed(store, args.asset_id, reviewer=args.reviewer,
                                       evidence=args.evidence)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

