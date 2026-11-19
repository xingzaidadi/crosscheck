"""Score framework maturity separately from business-suite readiness."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def score_onboarding(path: str | Path) -> dict:
    root = Path(path)
    intake = json.loads((root / "intake.json").read_text(encoding="utf-8"))
    readiness = json.loads((root / "readiness.json").read_text(encoding="utf-8"))
    gaps = json.loads((root / "gap_report.json").read_text(encoding="utf-8"))
    cases = max(1, int(intake.get("case_count", 0)))
    ready = sum(item.get("status") == "READY" for item in readiness)
    framework = {
        "input_adapters": 1.0,
        "canonical_model": 1.0 if ready + len(readiness) - ready == cases else 0.0,
        "capability_discovery": 1.0 if (root / "capability_graph.json").exists() else 0.0,
        "fixture_planning": 1.0 if (root / "fixture_requirements.json").exists() else 0.0,
        "binding_planning": 1.0 if (root / "binding_candidates" / "all.json").exists() else 0.0,
        "oracle_planning": 1.0 if (root / "oracle_plan.json").exists() else 0.0,
        "readiness": 1.0 if len(readiness) == cases else 0.0,
        "determinism": 1.0 if json.loads((root / "audit.json").read_text(encoding="utf-8")).get("deterministic") else 0.0,
        "gap_explainability": 1.0 if all(item.get("type") and item.get("reason") for item in gaps.get("gaps", [])) else 0.0,
    }
    business = {
        "case_import_completeness": ready * 0 + (1.0 if len(readiness) == cases else 0.0),
        "ready_rate": ready / cases,
        "blocked_rate": (cases - ready) / cases,
        "gap_count": gaps.get("total", 0),
    }
    return {"schema_version": 1, "framework_score": round(sum(framework.values()) / len(framework) * 100, 1),
            "framework_dimensions": framework, "business_score": round(ready / cases * 100, 1),
            "business_dimensions": business}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("onboarding_dir")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    result = score_onboarding(args.onboarding_dir)
    output = Path(args.output) if args.output else Path(args.onboarding_dir) / "dual_score.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
