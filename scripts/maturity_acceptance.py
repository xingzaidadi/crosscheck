"""Run the offline four-phase maturity acceptance against JSON samples."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.maturity_acceptance import evaluate_maturity


def main() -> int:
    parser = argparse.ArgumentParser(description="自主 UI 测试四阶段成熟度验收")
    parser.add_argument("--samples", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    samples = json.loads(Path(args.samples).read_text(encoding="utf-8-sig"))
    report = evaluate_maturity(samples)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
