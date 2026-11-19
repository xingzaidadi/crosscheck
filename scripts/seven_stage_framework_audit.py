"""Run machine checks for the framework-first seven-stage acceptance gates."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.framework_score import score_onboarding


def audit(onboarding_dir: str | Path, root: str | Path = ".") -> dict:
    onboarding = Path(onboarding_dir)
    root = Path(root).resolve()
    boundary_output = onboarding / "framework_boundary_audit.json"
    command = [sys.executable, str(root / "scripts" / "framework_boundary_audit.py"),
               "--root", str(root), "--output", str(boundary_output)]
    boundary_exit = subprocess.run(command, capture_output=True, text=True).returncode
    boundary = json.loads(boundary_output.read_text(encoding="utf-8")) if boundary_output.exists() else {}
    intake = json.loads((onboarding / "intake.json").read_text(encoding="utf-8"))
    readiness = json.loads((onboarding / "readiness.json").read_text(encoding="utf-8"))
    gaps = json.loads((onboarding / "gap_report.json").read_text(encoding="utf-8"))
    dual = score_onboarding(onboarding)
    case_count = intake.get("case_count", 0)
    stages = [
        {"stage": 1, "name": "boundary", "passed": boundary_exit == 0},
        {"stage": 2, "name": "unified_schema", "passed": all((onboarding / name).exists() for name in
         ("capability_graph.json", "coverage_matrix.json", "fixture_requirements.json", "oracle_plan.json"))},
        {"stage": 3, "name": "full_onboarding", "passed": len(readiness) == case_count},
        {"stage": 4, "name": "gap_completeness", "passed": all(item.get("type") and item.get("reason") for item in gaps.get("gaps", []))},
        {"stage": 5, "name": "migration_contract", "passed": bool(
            json.loads((onboarding / "cross_system_report.json").read_text(encoding="utf-8")).get("passed"))},
        {"stage": 6, "name": "full_acceptance_dataset", "passed": case_count > 0 and len(readiness) == case_count},
        {"stage": 7, "name": "dual_score", "passed": "framework_score" in dual and "business_score" in dual},
    ]
    result = {"schema_version": 1, "passed": all(item["passed"] for item in stages),
              "stages": stages, "case_count": case_count, "gap_count": gaps.get("total", 0),
              "dual_score": dual, "boundary": boundary}
    (onboarding / "seven_stage_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("onboarding_dir")
    args = parser.parse_args()
    result = audit(args.onboarding_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
