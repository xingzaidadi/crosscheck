"""Turn onboarding gaps into an explicit, non-speculative remediation queue."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def triage(onboarding_dir: str | Path) -> dict:
    root = Path(onboarding_dir)
    gaps = json.loads((root / "gap_report.json").read_text(encoding="utf-8"))
    readiness = {item["case_id"]: item for item in
                 json.loads((root / "readiness.json").read_text(encoding="utf-8"))}
    items = []
    for gap in gaps.get("gaps", []):
        kind = gap.get("type")
        if kind == "ENVIRONMENT_MISSING":
            disposition, owner = "ENVIRONMENT_BLOCKED", "environment"
        elif kind == "BUSINESS_INPUT_REQUIRED":
            disposition, owner = "BUSINESS_FACT_REQUIRED", "business-owner"
        elif kind == "FIXTURE_MISSING":
            disposition, owner = "FIXTURE_RECIPE_REQUIRED", "fixture-owner"
        elif kind == "BINDING_REVIEW_REQUIRED":
            disposition, owner = "CANDIDATE_REVIEW_REQUIRED", "binding-reviewer"
        elif kind == "ORACLE_REVIEW_REQUIRED":
            disposition, owner = "ORACLE_REVIEW_REQUIRED", "oracle-reviewer"
        elif kind == "MANUAL_ONLY":
            disposition, owner = "MANUAL_EXECUTION_REQUIRED", "test-owner"
        else:
            disposition, owner = "FRAMEWORK_CAPABILITY_REQUIRED", "framework-owner"
        items.append({**gap, "disposition": disposition, "owner": owner,
                      "case_status": readiness.get(gap.get("case_id"), {}).get("status", "UNKNOWN")})
    by_disposition = Counter(item["disposition"] for item in items)
    by_case = {}
    for item in items:
        record = by_case.setdefault(item["case_id"], {"case_id": item["case_id"], "items": [], "dispositions": []})
        record["items"].append(item["gap_id"])
        record["dispositions"].append(item["disposition"])
    for record in by_case.values():
        record["dispositions"] = sorted(set(record["dispositions"]))
        record["blocked"] = bool(record["items"])
    return {"schema_version": 1, "onboarding_dir": str(root), "total": len(items),
            "counts": dict(sorted(by_disposition.items())), "items": items,
            "cases": sorted(by_case.values(), key=lambda item: item["case_id"]),
            "policy": {"no_guessing": True, "candidate_assets_require_review": True,
                       "business_facts_are_not_inferred": True}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("onboarding_dir")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    result = triage(args.onboarding_dir)
    output = Path(args.output) if args.output else Path(args.onboarding_dir) / "gap_triage.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(output), "total": result["total"], "counts": result["counts"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
