"""Report and optionally persist approved-asset health."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.asset_health import aggregate_asset_health, update_approved_asset_health, write_asset_health  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="聚合 Fixture/Oracle 的运行健康度")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--output")
    parser.add_argument("--degrade-after", type=int, default=2)
    parser.add_argument("--unhealthy-after", type=int, default=3)
    parser.add_argument("--update-assets", action="store_true")
    args = parser.parse_args()
    suite = Path(args.suite)
    report = aggregate_asset_health(suite / "reports" / "runs",
                                    degrade_after=args.degrade_after,
                                    unhealthy_after=args.unhealthy_after)
    output = Path(args.output) if args.output else suite / "reports" / "asset_health.json"
    write_asset_health(report, output)
    updated = update_approved_asset_health(suite, report) if args.update_assets else []
    print(json.dumps({"report": str(output), "assets": report["asset_count"],
                      "updated_assets": updated, "health_counts": {
                          status: sum(item["health"] == status for item in report["assets"])
                          for status in ("healthy", "degraded", "unhealthy", "insufficient_data")
                      }}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
