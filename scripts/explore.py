"""Run safe read-only browser exploration for unresolved assertion candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.browser_explorer import explore_task
from core.suite_context import SuiteContext
from core.suite_dsl import load_suite
from core.suite_execution import build_execution_plan
from core.workspace import set_workspace


def main() -> int:
    parser = argparse.ArgumentParser(description="只读浏览器探索未匹配断言")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--only", help="case key or assertion id, comma separated")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--output")
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    suite_dir = Path(args.suite).resolve()
    set_workspace(workspace)
    suite, cases = load_suite(suite_dir)
    context = SuiteContext.create(suite_dir, workspace)
    _, lifecycle = build_execution_plan(suite, cases, context, suite_dir, phase="ui")
    wanted = {item.strip() for item in (args.only or "").split(",") if item.strip()}
    tasks = [item for item in lifecycle.get("assertion_candidates") or []
             if item.get("status") == "READY_TO_EXPLORE"
             and (not wanted or item.get("source_case_key") in wanted or item.get("assertion_id") in wanted)]
    tasks = tasks[:max(0, args.limit)]
    output = Path(args.output) if args.output else suite_dir / "reports" / "explorations"
    results = [explore_task(task, workspace=workspace, output=output) for task in tasks]
    report = {"schema_version": 1, "mode": "read_only_exploration", "suite": str(suite_dir),
              "selected": len(tasks), "results": results}
    report_path = output / "exploration_report.json"
    output.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path), "selected": len(tasks),
                      "statuses": {status: sum(item.get("status") == status for item in results)
                                   for status in sorted({item.get("status") for item in results})}},
                     ensure_ascii=False, indent=2))
    return 0 if all(item.get("status") == "REPLAY_VERIFIED" for item in results) else 4


if __name__ == "__main__":
    raise SystemExit(main())
