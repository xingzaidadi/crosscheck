"""Primary use-case-driven test entrypoint.

The case file is the source of truth. Supporting code, design and database
paths are read-only evidence inputs used for traceability and future planning.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.case_evidence import ingest_sources  # noqa: E402
from core.case_orchestration import build_case_plans, coverage_report  # noqa: E402
from core.case_source import read_cases  # noqa: E402
from scripts.agent_test import run as run_agent_test  # noqa: E402


def execute(args) -> dict:
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    cases = read_cases(args.cases)
    if args.only:
        wanted = {item.strip() for item in args.only.split(",") if item.strip()}
        cases = [case for case in cases if case.case_id in wanted or case.name in wanted]
    report_dir = workspace / "reports" / "case-runs" / (args.run_id or f"case_run_{time.strftime('%Y%m%d_%H%M%S')}")
    report_dir.mkdir(parents=True, exist_ok=True)
    sources = [item for item in (args.source or []) if item]
    source_manifest = ingest_sources(sources, report_dir / "source_manifest.json")
    plans = build_case_plans(cases, args.url, source_manifest)
    plan_payload = {"schema_version": 1, "cases": [item.to_dict() for item in plans],
                    "source_manifest": str(report_dir / "source_manifest.json")}
    (report_dir / "case_plan.json").write_text(json.dumps(plan_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.plan_only:
        coverage = coverage_report(plans, source_manifest=source_manifest)
        (report_dir / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "PLANNED", "report_dir": str(report_dir), "coverage": coverage,
                "source_manifest": source_manifest}
    results = []
    for index, item in enumerate(plans, start=1):
        request = SimpleNamespace(
            url=args.url, instruction=item.instruction, workspace=str(workspace), role=item.role or args.role,
            session=args.session, risk_policy=args.risk_policy, allow_write=args.allow_write,
            write_scope=args.write_scope or "",
            run_id=f"{report_dir.name}-{index:03d}-{item.case_id.replace('/', '-')}",
            max_steps=args.max_steps, headed=args.headed, no_persist=args.no_persist,
            no_session_refresh=args.no_session_refresh, interactive_login=args.interactive_login,
        )
        result = run_agent_test(request)
        result["case_id"] = item.case_id
        result["title"] = item.title
        results.append(result)
    coverage = coverage_report(plans, results, source_manifest)
    statuses = {str(item.get("status") or "") for item in results}
    output_status = "PASSED" if results and statuses == {"PASSED"} else \
        "FAILED" if statuses & {"FAILED", "ENV_ERROR", "BLOCKED"} else "COMPLETED"
    output = {"status": output_status,
              "report_dir": str(report_dir), "results": results, "coverage": coverage,
              "source_manifest": source_manifest}
    (report_dir / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_dir / "summary.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="用例驱动的自主 UI 测试")
    parser.add_argument("--cases", required=True, help="xlsx/csv/json 用例文件")
    parser.add_argument("--url", required=True)
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--source", action="append", help="代码、技术方案、数据库 schema 或目录，可重复")
    parser.add_argument("--only")
    parser.add_argument("--role", default="default")
    parser.add_argument("--session")
    parser.add_argument("--risk-policy", choices=("read_only", "authorized_write"), default="read_only")
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--write-scope")
    parser.add_argument("--run-id")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--interactive-login", action="store_true", default=True)
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--no-session-refresh", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    result = execute(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"PASSED", "PLANNED", "COMPLETED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
