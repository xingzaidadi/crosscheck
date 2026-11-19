"""System discovery and deterministic full-suite onboarding entry point."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.framework import (build_capability_graph, canonicalize, fingerprint, validate_document,
                            load_document, load_suite_assets, plan_onboarding, schemas)  # noqa: E402
from core.onboard import scan_all  # noqa: E402
from core.workspace import set_workspace  # noqa: E402
from core.gap_resolutions import (apply_resolutions, load_resolutions, validate_resolutions,
                                 write_template)  # noqa: E402


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def cmd_onboard(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    set_workspace(workspace)
    cases_path = Path(args.cases).resolve()
    profile = load_document(args.profile) if args.profile else {}
    if not isinstance(profile, dict):
        raise SystemExit("profile must be a mapping")
    requirements = load_document(args.requirements) if args.requirements else None
    suite_assets = load_suite_assets(args.suite_assets)
    resolution_data = load_resolutions(args.resolutions) if args.resolutions else None
    input_value = {"cases": load_document(cases_path), "requirements": requirements, "profile": profile,
                   "resolutions": resolution_data, "suite_asset_fingerprint": suite_assets.get("fingerprint", "")}
    input_fingerprint = fingerprint(input_value)
    onboarding_id = f"onboarding-{input_fingerprint[:16]}"
    output = workspace / "onboarding" / onboarding_id
    output.mkdir(parents=True, exist_ok=True)

    cases = canonicalize(cases_path, str(profile.get("suite_id") or cases_path.stem))
    canonical_dir = output / "canonical_suite"
    canonical_dir.mkdir(exist_ok=True)
    for index, case in enumerate(cases, 1):
        filename = f"case-{index:05d}.json"
        _write_json(canonical_dir / filename, case.to_dict())

    graph = build_capability_graph(profile, workspace)
    plan = plan_onboarding(cases, graph, profile, suite_assets)
    resolution_audit = {"schema_version": 1, "status": "NOT_PROVIDED", "submitted": 0, "approved": 0}
    if args.resolutions:
        plan, resolution_audit = apply_resolutions(plan, resolution_data)
    _write_json(output / "intake.json", {"schema_version": 1, "cases": str(cases_path),
                                          "requirements": args.requirements or "", "profile": args.profile or "",
                                          "suite_assets": args.suite_assets or "",
                                          "resolutions": args.resolutions or "",
                                          "case_count": len(cases), "fingerprint": input_fingerprint})
    _write_json(output / "capability_graph.json", graph.to_dict())
    schema_dir = output / "schemas"
    for name, schema in schemas().items():
        _write_json(schema_dir / f"{name}.schema.json", schema)
    _write_json(output / "intent_matrix.json", [case.to_dict() for case in cases])
    for name in ("coverage_matrix", "fixture_requirements", "oracle_plan", "readiness", "gap_report"):
        _write_json(output / f"{name}.json", plan[name])
    _write_json(output / "binding_candidates" / "all.json", plan["binding_candidates"])
    _write_json(output / "resolution_audit.json", resolution_audit)
    _write_json(output / "resolved_configuration.json", resolution_audit.get("resolved_assets", {}))
    write_template(plan["gap_report"], output / "gap_resolutions.template.yaml", resolution_data)
    ready_ids = [item["case_id"] for item in plan["readiness"] if item["status"] == "READY"]
    _write_json(output / "execution_plan.json", {"schema_version": 1, "mode": "ready_only",
                                                  "case_ids": ready_ids})
    serialized_cases = [case.to_dict() for case in cases]
    schema_errors = []
    for case in serialized_cases:
        schema_errors.extend(validate_document(case, schemas()["canonical_case"]))
    output_fingerprint = fingerprint({"graph": graph.to_dict(), "plan": plan,
                                      "canonical_cases": serialized_cases})
    repeated_plan = plan_onboarding(cases, graph, profile, suite_assets)
    repeated_fingerprint = fingerprint({"graph": graph.to_dict(), "plan": repeated_plan,
                                        "canonical_cases": serialized_cases})
    resolution_deterministic = True
    if resolution_data:
        repeated_plan, _ = apply_resolutions(repeated_plan, resolution_data)
        resolved_fingerprint = fingerprint({"graph": graph.to_dict(), "plan": plan,
                                            "canonical_cases": serialized_cases})
        repeated_resolved_fingerprint = fingerprint({"graph": graph.to_dict(), "plan": repeated_plan,
                                                     "canonical_cases": serialized_cases})
        resolution_deterministic = resolved_fingerprint == repeated_resolved_fingerprint
        repeated_fingerprint = repeated_resolved_fingerprint
    deterministic = (output_fingerprint == repeated_fingerprint if not resolution_data
                     else resolution_deterministic)
    audit = {"schema_version": 1, "onboarding_id": onboarding_id, "input_fingerprint": input_fingerprint,
             "case_count": len(cases), "readiness_count": len(plan["readiness"]),
             "gap_count": plan["gap_report"]["total"], "deterministic": deterministic,
             "schema_valid": not schema_errors, "schema_errors": schema_errors,
             "output_fingerprint": output_fingerprint, "repeated_fingerprint": repeated_fingerprint,
             "resolution_fingerprint": fingerprint(resolution_data) if resolution_data else ""}
    _write_json(output / "audit.json", audit)
    _write_json(output / "framework_audit.json", audit)
    resolution_errors = validate_resolutions(resolution_data) if resolution_data else []
    _write_json(output / "schema_validation.json", {"schema_version": 1,
                                                      "passed": not schema_errors and not resolution_errors,
                                                      "validated_cases": len(serialized_cases),
                                                      "errors": schema_errors + resolution_errors,
                                                      "schemas": sorted(schemas())})
    _write_json(output / "determinism_report.json", {"schema_version": 1, "passed": deterministic,
                                                      "input_fingerprint": input_fingerprint,
                                                      "output_fingerprint": output_fingerprint,
                                                      "repeated_fingerprint": repeated_fingerprint})
    boundary_path = workspace / "framework_boundary_audit.json"
    leakage = json.loads(boundary_path.read_text(encoding="utf-8")) if boundary_path.exists() else {
        "schema_version": 1, "passed": False, "status": "BOUNDARY_AUDIT_NOT_RUN"}
    _write_json(output / "business_leakage_report.json", leakage)
    _write_json(output / "cross_system_report.json", {"schema_version": 1, "status": "NOT_RUN",
                                                        "passed": False,
                                                        "reason": "second-system migration validation is a separate acceptance gate"})
    _write_json(output / "test_results.json", {"schema_version": 1, "status": "ONBOARD_SELF_CHECKS",
                                                "passed": not schema_errors and deterministic,
                                                "schema_validation": not schema_errors,
                                                "determinism": deterministic})
    execution = None
    if args.execute_ready:
        if not args.suite_assets:
            raise SystemExit("--execute-ready requires --suite-assets pointing to an approved canonical suite")
        from scripts.execute_onboarding import execute
        execution = execute(output, args.suite_assets, workspace,
                            ensure_login=args.ensure_login, pilot_size=args.pilot_size)
    print(json.dumps({"onboarding_id": onboarding_id, "output": str(output), "case_count": len(cases),
                      "ready_count": len(ready_ids), "gap_count": plan["gap_report"]["total"],
                      "execution": execution},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    report = scan_all(args.url, site=args.site, code_path=args.code_path, db_name=args.db,
                      context=args.context or "", session_file=args.session, write=not args.no_write)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover a system or run deterministic full-suite onboarding")
    sub = parser.add_subparsers(dest="cmd", required=True)

    onboard = sub.add_parser("onboard", help="import, model, plan, and report all gaps in one pass")
    onboard.add_argument("--requirements", default=None, help="requirements file or directory")
    onboard.add_argument("--cases", required=True, help="case file")
    onboard.add_argument("--profile", default=None, help="system profile")
    onboard.add_argument("--suite-assets", default=None, help="existing suite assets for candidate reuse")
    onboard.add_argument("--resolutions", default=None, help="reviewed gap resolution YAML or JSON")
    onboard.add_argument("--execute-ready", action="store_true", help="execute the intersection of onboarding READY and approved suite cases")
    onboard.add_argument("--ensure-login", action="store_true", help="ensure required sessions before execution")
    onboard.add_argument("--pilot-size", type=int, default=3, help="safe pilot size before batch expansion")
    onboard.add_argument("--workspace", default="workspace", help="workspace root")
    onboard.set_defaults(func=cmd_onboard)

    scan = sub.add_parser("scan", help="discover site, database, and source capabilities")
    scan.add_argument("--url", required=True)
    scan.add_argument("--site", default=None)
    scan.add_argument("--code-path", default=None)
    scan.add_argument("--db", default=None)
    scan.add_argument("--context", default="")
    scan.add_argument("--session", default=None)
    scan.add_argument("--workspace", default=None)
    scan.add_argument("--no-write", action="store_true")
    scan.set_defaults(func=cmd_scan)

    args = parser.parse_args()
    if args.workspace:
        set_workspace(args.workspace)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
