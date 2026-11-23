"""Report business-domain capability coverage for a canonical suite."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.domain_capability_readiness import assess_domain_capabilities  # noqa: E402
from core.suite_dsl import load_suite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="评估业务域能力包覆盖率")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--registry")
    parser.add_argument("--environment", default="test")
    parser.add_argument("--output")
    args = parser.parse_args()
    suite, cases = load_suite(args.suite)
    registry = args.registry or str(Path(args.workspace) / "config" / "capabilities.yaml")
    report = assess_domain_capabilities(cases, registry_path=registry, environment=args.environment)
    report["suite_id"] = suite.get("suite_id", "")
    output = Path(args.output) if args.output else Path(args.suite) / "reports" / "domain_capability_coverage.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"suite_id": report["suite_id"], "output": str(output),
                      "capability_pack_valid": report["capability_pack_valid"],
                      "coverage": report["coverage"],
                      "missing_action_kinds": report["missing_action_kinds"]}, ensure_ascii=False, indent=2))
    return 0 if report["capability_pack_valid"] and not report["missing_action_kinds"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
