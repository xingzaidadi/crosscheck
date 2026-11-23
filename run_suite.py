"""Unified canonical suite entry: score first, then run only approved executable specs."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.suite_dsl import load_suite, score_suite, write_score
from core.suite_execution import build_execution_plan, write_execution_plan, write_lifecycle_report
from core.suite_context import SuiteContext
from core.workspace import set_workspace
from core.reporter import Reporter
from core import run_report
from core.pipeline_runner import run_pipeline
from core.run_events import append_event
from run_batch import execute, finalize_result


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="校验、评分并执行隔离测试套件")
    parser.add_argument("--suite", required=True, help="workspace/suites/<suite-id> 目录")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--score-only", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--only", default=None)
    parser.add_argument("--ensure-login", action="store_true")
    parser.add_argument("--pilot-size", type=int, default=3)
    parser.add_argument("--run-all-selected", action="store_true",
                        help="执行全部已选 READY 用例，不因 pilot 熔断")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--ui-first", action="store_true")
    args = parser.parse_args()
    suite_dir = Path(args.suite).resolve()
    workspace = Path(args.workspace).resolve()
    context = SuiteContext.create(suite_dir, workspace)
    set_workspace(workspace)
    suite, cases = load_suite(suite_dir)
    score = score_suite(suite, cases)
    reports = suite_dir / "reports"
    score_path = write_score(score, reports / "suite_score.json")
    print(f"[suite] {score['suite_id']} · schema={score['schema_valid']}/{score['total']}"
          f" · compile_candidates={score['execution_ready']} · structure_score={score['average_score']}")
    print(f"[suite] 评分: {score_path}")
    if args.score_only:
        return 0
    authorization = suite.get("authorization") or {}
    if not authorization.get("confirmed_non_production"):
        print("[suite] 未确认非生产环境: suite.authorization.confirmed_non_production 必须为 true")
        return 6
    phase = "ui" if args.ui_first else "all"
    specs, lifecycle = build_execution_plan(suite, cases, context, suite_dir, phase=phase)
    lifecycle_path = write_lifecycle_report(lifecycle, reports / "execution_readiness.json")
    if args.only:
        wanted = {value.strip() for value in args.only.split(",") if value.strip()}
        specs = [spec for spec in specs if spec.case_id in wanted
                 or spec.raw.get("canonical_case_id") in wanted
                 or spec.raw.get("canonical_case_key") in wanted
                 or str(spec.raw.get("canonical_case_key") or "").split("/")[-1] in wanted]
    invalid = lifecycle["invalid"]
    plan_path = write_execution_plan(specs, lifecycle, reports / "execution_plan.json")
    print(f"[suite] execution_ready={lifecycle['execution_ready']} selected={len(specs)}"
          f" invalid={len(invalid)} plan={plan_path}")
    print(f"[suite] lifecycle={lifecycle_path}")
    if invalid:
        invalid_path = reports / "invalid_cases.json"
        import json
        invalid_path.write_text(json.dumps(invalid, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[suite] invalid cases: {invalid_path}")
    if args.plan_only:
        return 0
    if not specs and not invalid:
        print("[suite] 没有 execution_ready case；详见 lifecycle 缺口报告。")
        return 2

    run_id = args.run_id or f"suite_{suite['suite_id']}_{time.strftime('%Y%m%d_%H%M%S')}"
    if Path(run_id).name != run_id or run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
        raise ValueError("run-id must be a single safe directory name")
    run_dir = reports / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.ensure_login:
        from core.session_ensure import ensure_batch_sessions
        actions = ensure_batch_sessions(specs)
        if any(item.get("action") == "error" for item in actions):
            print(f"[suite] session ensure failed: {actions}")
            return 3

    def execute_with_events(spec):
        append_event(run_dir, run_id=run_id, case_id=spec.case_id,
                     state="running", assertion_ids=list((spec.raw or {}).get("assertion_ids") or []))
        result = finalize_result(spec, execute(spec, False, run_dir, False, False, phase=phase), phase=phase)
        asset_usage = (spec.raw or {}).get("approved_assets") or {}
        if asset_usage:
            result.report = {
                **(result.report or {}),
                "asset_usage": asset_usage,
            }
        append_event(run_dir, run_id=run_id, case_id=spec.case_id,
                     state="succeeded" if result.verdict.value == "pass" else "failed",
                     failure_class=result.failure_class,
                     assertion_ids=result.executed_assertions,
                     detail="; ".join(result.details))
        return result

    outcome = run_pipeline(
        specs,
        execute_with_events,
        run_dir,
        pilot_size=0 if args.run_all_selected else args.pilot_size,
        resume=not args.no_resume,
    )
    results = outcome.results
    from core.interfaces import CaseResult, Verdict
    results.extend(CaseResult(case_id=item["case_id"], verdict=Verdict.INVALID_SPEC,
                              details=[item["error"]], title=item["case_id"], kind="canonical", mode="compile")
                   for item in invalid)
    reporter = Reporter()
    for result in results:
        reporter.add(result)
    print("\n" + reporter.render())
    report_path = run_report.render(run_id, results, run_dir)
    print(f"[suite] report={report_path}")
    if outcome.stopped:
        print(f"[suite] pipeline stopped: {outcome.reason}")
    summary = reporter.summary()
    if summary["cleanup_failed"] or outcome.stopped:
        return 5
    if summary["fail"] or summary["env_error"] or summary["aborted"] or summary["partial"] or summary["invalid_spec"]:
        return 1
    if summary["skip"] or summary["blocked"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
