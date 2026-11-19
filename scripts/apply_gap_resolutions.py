"""Apply reviewed gap answers to an existing onboarding output."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.gap_resolutions import apply_resolutions, load_resolutions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("onboarding_dir")
    parser.add_argument("resolutions")
    args = parser.parse_args()
    root = Path(args.onboarding_dir)
    plan = {
        "gap_report": json.loads((root / "gap_report.json").read_text(encoding="utf-8")),
        "readiness": json.loads((root / "readiness.json").read_text(encoding="utf-8")),
        "binding_candidates": json.loads((root / "binding_candidates" / "all.json").read_text(encoding="utf-8")),
        "oracle_plan": json.loads((root / "oracle_plan.json").read_text(encoding="utf-8")),
        "fixture_requirements": json.loads((root / "fixture_requirements.json").read_text(encoding="utf-8")),
    }
    plan, audit = apply_resolutions(plan, load_resolutions(args.resolutions))
    mapping = {"gap_report": root / "gap_report.json", "readiness": root / "readiness.json",
               "binding_candidates": root / "binding_candidates" / "all.json",
               "oracle_plan": root / "oracle_plan.json", "fixture_requirements": root / "fixture_requirements.json"}
    for key, path in mapping.items():
        path.write_text(json.dumps(plan[key], ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (root / "resolution_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2,
                                                            sort_keys=True), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
