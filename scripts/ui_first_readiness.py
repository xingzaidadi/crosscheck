"""Produce a UI-first readiness matrix for a canonical suite."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.framework import load_suite_assets
from core.suite_dsl import load_suite


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--plan", help="Optional compiled suite_plan.json with merged reviewed specs")
    parser.add_argument("--output")
    args = parser.parse_args()
    suite, cases = load_suite(args.suite)
    assets = load_suite_assets(args.suite)
    asset_bindings = assets.get("bindings") or {}
    compiled = {}
    if args.plan:
        plan_data = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        compiled = {str(item.get("case_id")): item for item in plan_data.get("cases") or []}
    rows = []
    for case in cases:
        source_key = str((case.get("source") or {}).get("case_key") or "")
        compiled_case = compiled.get(source_key) or compiled.get(str(case.get("case_id"))) or {}
        execution = case.get("execution") or {}
        ui_actions = (case.get("actions") or {}).get("ui") or []
        suite_binding = asset_bindings.get(source_key) or asset_bindings.get(str(case.get("case_id"))) or {}
        provided = set(compiled_case.get("provided_layers") or [])
        ui_asset = suite_binding.get("ui") or {}
        has_ui = bool("ui" in provided or ui_asset or execution.get("mode") == "ui" or execution.get("ui") or ui_actions)
        binding_health = str(ui_asset.get("health") or "verified")
        blocked = str(compiled_case.get("blocked") or case.get("blocked") or "")
        if binding_health not in {"", "verified", "db_oracle_incomplete", "api_oracle_incomplete", "cross_layer_incomplete"}:
            blocked = blocked or f"binding health: {binding_health}"
        approval = case.get("approval") or {}
        approved = bool(
            compiled_case.get("verify_status") == "human_verified"
            or approval.get("status") == "human_verified"
            or ui_asset.get("verified")
        )
        if blocked:
            status, reason = "UI_BLOCKED", blocked
        elif has_ui and approved:
            status, reason = "UI_EXECUTABLE", "approved UI binding"
        elif has_ui:
            status, reason = "UI_REVIEW_REQUIRED", "UI binding exists but is not human_verified"
        else:
            status, reason = "UI_BINDING_REQUIRED", "no UI action binding"
        rows.append({"case_id": case.get("case_id"), "title": case.get("title"),
                     "status": status, "reason": reason,
                     "api": "OPTIONAL", "db": "OPTIONAL"})
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    report = {"suite_id": suite.get("suite_id"), "phase": "ui", "total": len(rows),
              "counts": counts, "cases": rows}
    output = Path(args.output) if args.output else Path(args.suite) / "reports" / "ui_first_readiness.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
