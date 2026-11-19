"""Compare two onboarding runs and emit a schema-compatible migration report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compare(first: str | Path, second: str | Path) -> dict:
    first, second = Path(first), Path(second)
    intake_a = json.loads((first / "intake.json").read_text(encoding="utf-8"))
    intake_b = json.loads((second / "intake.json").read_text(encoding="utf-8"))
    required = ["capability_graph.json", "coverage_matrix.json", "fixture_requirements.json",
                "binding_candidates/all.json", "oracle_plan.json", "readiness.json", "gap_report.json"]
    missing = {"first": [name for name in required if not (first / name).exists()],
               "second": [name for name in required if not (second / name).exists()]}
    result = {"schema_version": 1, "passed": not missing["first"] and not missing["second"],
              "systems": [{"path": str(first), "case_count": intake_a.get("case_count")},
                          {"path": str(second), "case_count": intake_b.get("case_count")}],
              "required_outputs": required, "missing": missing,
              "output_schema_equal": all((first / name).exists() == (second / name).exists() for name in required)}
    result["passed"] = result["passed"] and result["output_schema_equal"]
    for root in (first, second):
        (root / "cross_system_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                                                    sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("first")
    parser.add_argument("second")
    args = parser.parse_args()
    result = compare(args.first, args.second)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
