"""Run the diff-triggered review gate (base-branch REVIEW.md vs current change)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.review_gate import build_review_gate, write_review_gate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="按基线分支 REVIEW.md 对当前改动做 diff 触发审查清单")
    parser.add_argument("--base-ref", default="main")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = build_review_gate(args.repo, base_ref=args.base_ref)
    if args.output:
        write_review_gate(report, args.output)
    print(json.dumps({
        "rules_source": report["rules_source"],
        "rules_active": report["rules_active"],
        "warnings": report["warnings"],
        "changed_files": len(report["changed_files"]),
        "matched_rules": [r["name"] for r in report["matched_rules"]],
        "next_actions": report["next_actions"],
        "content_hash": report["content_hash"],
    }, ensure_ascii=False, indent=2))
    for warning in report["warnings"]:
        print(f"WARNING: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
