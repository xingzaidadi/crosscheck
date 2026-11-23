"""Aggregate consecutive suite runs into a soak stability report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.soak_report import aggregate_soak, build_soak_summary, write_soak  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="聚合连续运行为 soak 稳定性报告")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--min-runs", type=int, default=5)
    parser.add_argument("--output")
    parser.add_argument("--summary-output", help="写出一个 quality-gate 可用的合并 summary.json")
    args = parser.parse_args()
    runs_root = Path(args.suite) / "reports" / "runs"
    report = aggregate_soak(runs_root, min_runs=args.min_runs)
    output = Path(args.output) if args.output else Path(args.suite) / "reports" / "soak_report.json"
    write_soak(report, output)
    summary_path = None
    if args.summary_output:
        summary_path = Path(args.summary_output)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(build_soak_summary(report), ensure_ascii=False, indent=2),
                                encoding="utf-8")
    print(json.dumps({"output": str(output), "summary_output": str(summary_path) if summary_path else None,
                      "soak_runs": report["soak_runs"], "stability": report["stability"],
                      "meets_min_runs": report["meets_min_runs"],
                      "all_runs_passed": report["all_runs_passed"]}, ensure_ascii=False, indent=2))
    return 0 if report["meets_min_runs"] and report["all_runs_passed"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
