"""Suggest REVIEW.md rules to prune (redundant / never-matched) — suggest only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.rule_lifecycle import prune_rules  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="提议可清理的 REVIEW.md 规则（默认只提议，不删）")
    parser.add_argument("--review", default="REVIEW.md")
    parser.add_argument("--usage", help="规则命中次数 JSON（{name: count}），给了才按未命中提议")
    parser.add_argument("--output")
    args = parser.parse_args()

    review_text = Path(args.review).read_text(encoding="utf-8") if Path(args.review).exists() else ""
    usage = json.loads(Path(args.usage).read_text(encoding="utf-8")) if args.usage else None
    result = prune_rules(review_text, usage=usage)
    report = {"keep": len(result["keep"]),
              "prune": [{"name": r["name"], "reason": r["prune_reason"]} for r in result["prune"]]}
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
