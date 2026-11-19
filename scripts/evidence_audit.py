"""Audit suite evidence requirements by objective rather than technology name."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.evidence_sufficiency import assess_evidence, infer_objective
from core.suite_dsl import load_suite


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    suite, cases = load_suite(args.suite)
    rows = []
    for case in cases:
        objective = infer_objective(case)
        layers = set((case.get("layers") or {}).get("required") or [])
        assessment = assess_evidence(objective, layers, assertions_passed=True)
        rows.append({"case_id": case.get("case_id"), "objective": objective,
                     "declared_layers": sorted(layers), "evidence_requirement": assessment})
    report = {"suite_id": suite.get("suite_id"), "total": len(rows),
              "transport_scope": sum(item["objective"] == "integration_transport" for item in rows),
              "cases": rows}
    output = Path(args.output) if args.output else Path(args.suite) / "reports" / "evidence_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
