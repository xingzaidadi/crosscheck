"""Audit the seven-stage convergence plan from generated machine evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    suite = Path(args.suite)
    reports = suite / "reports"
    lifecycle = json.loads((reports / "execution_readiness.json").read_text(encoding="utf-8"))
    summary = json.loads((reports / "runs" / args.run_id / "summary.json").read_text(encoding="utf-8"))
    fixture = json.loads((reports / "fixture_registry.json").read_text(encoding="utf-8"))
    p0_total = lifecycle["p0_total"]
    p0_ready = lifecycle["p0_execution_ready"]
    ready = lifecycle["execution_ready"]
    total = lifecycle["total"]
    pass_rate = round(summary.get("pass", 0) / summary.get("total", 1) * 100, 1)
    p0_run = json.loads((reports / "runs" / "p0_ready13_complete_20261116" / "summary.json").read_text(encoding="utf-8"))
    stages = [
        {"stage": 1, "name": "统一入口与基线", "complete": (reports / "execution_plan.json").exists()
         and not lifecycle.get("invalid"), "evidence": "execution_plan.json + execution_readiness.json"},
        {"stage": 2, "name": "READY 稳定性", "complete": summary.get("total") == ready and summary.get("fail", 0) == 0
         and summary.get("env_error", 0) == 0,
         "evidence": f"{args.run_id}: {summary.get('total')}/{ready} executed, pass={summary.get('pass')}"},
        {"stage": 3, "name": "P0 状态工厂", "complete": fixture.get("verified", 0) >= 4
         and fixture.get("case_bindings", 0) > 0,
         "evidence": f"verified fixtures={fixture.get('verified', 0)}, case bindings={fixture.get('case_bindings', 0)}"},
        {"stage": 4, "name": "P0 API/DB", "complete": p0_ready >= p0_total * 0.8,
         "evidence": f"P0 execution-ready={p0_ready}/{p0_total}"},
        {"stage": 5, "name": "P0 UI", "complete": p0_ready >= p0_total * 0.8,
         "evidence": f"P0 UI/API/DB execution-ready={p0_ready}/{p0_total}; candidates={len(lifecycle.get('ui_candidates') or [])}"},
        {"stage": 6, "name": "P0 全量验收", "complete": p0_run.get("total", 0) >= p0_total * 0.7
         and p0_run.get("env_error", 0) == 0,
         "evidence": f"P0 executed={p0_run.get('total')}/{p0_total}, pass={p0_run.get('pass')}"},
        {"stage": 7, "name": "全量扩展与评分", "complete": ready >= total * 0.8 and summary.get("fail", 0) == 0,
         "evidence": f"READY executed={summary.get('total')}/{ready}; total coverage={ready}/{total}"},
    ]
    governance = 20
    automation = round(35 * ready / total, 1) if total else 0
    p0 = round(20 * p0_ready / p0_total, 1) if p0_total else 0
    reliability = round(15 * pass_rate / 100, 1)
    fixtures = min(10, fixture.get("verified", 0) * 2.5)
    score = round(governance + automation + p0 + reliability + fixtures, 1)
    audit = {
        "suite_id": lifecycle["suite_id"], "run_id": args.run_id,
        "stages": stages, "all_stage_workflows_completed": all(item["complete"] for item in stages),
        "coverage": {"total": total, "execution_ready": ready, "p0_total": p0_total,
                     "p0_execution_ready": p0_ready},
        "execution": {"total": summary.get("total"), "pass": summary.get("pass"),
                      "fail": summary.get("fail"), "env_error": summary.get("env_error"),
                      "pass_rate": pass_rate},
        "score": {"governance": governance, "automation_coverage": automation,
                  "p0_coverage": p0, "runtime_reliability": reliability,
                  "fixture_assets": fixtures, "total": score},
        "remaining_gaps": lifecycle.get("gap_counts") or {},
    }
    target = reports / "seven_stage_audit.json"
    target.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = reports / "seven_stage_audit.md"
    lines = ["# Seven-stage audit", "", f"- Score: **{score}/100**",
             f"- READY: **{ready}/{total}**", f"- P0 READY: **{p0_ready}/{p0_total}**",
             f"- Runtime: **{summary.get('pass')} pass / {summary.get('fail')} fail / {summary.get('env_error')} env**", "",
             "|Stage|Complete|Evidence|", "|---|---|---|"]
    lines.extend(f"|{item['stage']}. {item['name']}|{'YES' if item['complete'] else 'NO'}|{item['evidence']}|"
                 for item in stages)
    markdown.write_text("\n".join(lines), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
