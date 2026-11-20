"""Run real-browser autonomous UI maturity scenarios."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.ui_agent.benchmark import run_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="真实浏览器自主 UI Agent 成熟度基准")
    parser.add_argument("--output", required=True)
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args()
    report = run_benchmark(args.output, repetitions=args.repetitions)
    print(json.dumps(report["maturity"], ensure_ascii=False, indent=2))
    return 0 if report["maturity"]["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
