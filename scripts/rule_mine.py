"""Mine recurring failures from run evidence into REVIEW.md rule candidates (suggest only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.rule_mining import mine_candidates  # noqa: E402
from core.circuit_breaker import read_handoffs  # noqa: E402
from core.rule_lifecycle import propose_rules  # noqa: E402
from core.review_rules import parse_review_md  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="从运行证据提炼 REVIEW.md 规则候选（默认只提议）")
    parser.add_argument("--runs", required=True, help="reports/runs 目录")
    parser.add_argument("--handoffs", help="blocked_needs_human.jsonl 所在目录")
    parser.add_argument("--review", default="REVIEW.md", help="现有 REVIEW.md 路径（去重用）")
    parser.add_argument("--min-occurrences", type=int, default=2)
    parser.add_argument("--output")
    parser.add_argument("--apply", action="store_true",
                        help="显式开启才把新候选追加进工作区 REVIEW.md；默认只提议")
    args = parser.parse_args()

    handoffs = read_handoffs(args.handoffs) if args.handoffs else []
    candidates = mine_candidates(args.runs, handoffs=handoffs, min_occurrences=args.min_occurrences)
    review_text = Path(args.review).read_text(encoding="utf-8") if Path(args.review).exists() else ""
    proposal = propose_rules(candidates, review_text)

    report = {
        "candidates_total": len(candidates),
        "new_candidates": proposal["new_candidates"],
        "duplicates": len(proposal["duplicates"]),
        "review_md_snippet": proposal["review_md_snippet"],
        "applied": False,
    }
    if args.apply and proposal["new_candidates"]:
        path = Path(args.review)
        prior = path.read_text(encoding="utf-8") if path.exists() else ""
        existing_names = {r["name"] for r in parse_review_md(prior)}
        # Skip candidates whose rule name already exists so repeated --apply can't dup blocks.
        fresh = [c for c in proposal["new_candidates"] if c["name"] not in existing_names]
        if fresh:
            from core.rule_lifecycle import _rule_to_md
            snippet = "\n".join(_rule_to_md(c) for c in fresh)
            path.write_text(prior.rstrip() + "\n\n" + snippet, encoding="utf-8")
            report["applied"] = True
            report["applied_count"] = len(fresh)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"candidates_total": report["candidates_total"],
                      "new_candidates": len(report["new_candidates"]),
                      "duplicates": report["duplicates"], "applied": report["applied"]},
                     ensure_ascii=False, indent=2))
    if not args.apply and proposal["new_candidates"]:
        print("\n提议的 REVIEW.md 片段（人审后再决定是否贴入；默认未写入）:\n", file=sys.stderr)
        print(proposal["review_md_snippet"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
