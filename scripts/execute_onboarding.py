"""Execute only onboarding cases also approved by the canonical suite runner."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.suite_context import SuiteContext
from core.suite_dsl import load_suite
from core.suite_execution import build_execution_plan
from core.workspace import set_workspace


def select_ready_cases(onboarding_dir: str | Path, suite_dir: str | Path,
                       workspace: str | Path) -> tuple[list[str], dict]:
    onboarding = Path(onboarding_dir).resolve()
    suite_root = Path(suite_dir).resolve()
    workspace_root = Path(workspace).resolve()
    readiness = json.loads((onboarding / "readiness.json").read_text(encoding="utf-8"))
    onboarding_ready = set()
    for item in readiness:
        if item.get("status") != "READY":
            continue
        tail = str(item["case_id"]).rsplit("/", 1)[-1]
        onboarding_ready.add(re.sub(r"-\d+$", "", tail))
    set_workspace(workspace_root)
    suite, cases = load_suite(suite_root)
    context = SuiteContext.create(suite_root, workspace_root)
    _, lifecycle = build_execution_plan(suite, cases, context, suite_root)
    executable = {row["case_id"] for row in lifecycle["cases"] if row.get("execution_ready")}
    matched = []
    reasons = []
    for case in cases:
        key = str((case.get("source") or {}).get("case_key") or "")
        if key in onboarding_ready and key in executable:
            matched.append(key)
        elif key in onboarding_ready:
            reasons.append({"case_id": case.get("case_id"), "source_case_key": key,
                            "reason": "onboarding READY but canonical suite is not execution-ready"})
    return sorted(set(matched)), {"onboarding_ready": len(onboarding_ready), "suite_execution_ready": len(executable),
                                  "selected": sorted(set(matched)), "excluded": reasons,
                                  "canonical_suite_id": suite.get("suite_id")}


def execute(onboarding_dir: str | Path, suite_dir: str | Path, workspace: str | Path, *,
            ensure_login: bool = False, pilot_size: int = 3) -> dict:
    onboarding = Path(onboarding_dir).resolve()
    suite = Path(suite_dir).resolve()
    workspace = Path(workspace).resolve()
    selected, selection = select_ready_cases(onboarding, suite, workspace)
    result = {"schema_version": 1, "status": "NOT_RUN", "selection": selection,
              "run_id": "", "exit_code": None, "report": "", "command": []}
    if not selected:
        result["status"] = "NO_EXECUTABLE_READY_CASES"
        (onboarding / "execution_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                                                         sort_keys=True), encoding="utf-8")
        return result
    run_id = f"onboard_{int(time.time())}"
    command = [sys.executable, str(ROOT / "run_suite.py"), "--suite", str(suite), "--workspace", str(workspace),
               "--only", ",".join(selected), "--pilot-size", str(pilot_size), "--run-id", run_id]
    if ensure_login:
        command.append("--ensure-login")
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    report_path = suite / "reports" / "runs" / run_id / "report.html"
    summary_path = suite / "reports" / "runs" / run_id / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    result.update({"status": "COMPLETED" if completed.returncode == 0 else "FAILED_OR_BLOCKED",
                   "run_id": run_id, "exit_code": completed.returncode,
                   "report": str(report_path) if report_path.exists() else "",
                   "summary": summary, "stdout": completed.stdout, "stderr": completed.stderr,
                   "command": command})
    (onboarding / "execution_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                                                     sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("onboarding_dir")
    parser.add_argument("--suite", required=True, help="approved canonical suite directory")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--ensure-login", action="store_true")
    parser.add_argument("--pilot-size", type=int, default=3)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if args.plan_only:
        selected, selection = select_ready_cases(args.onboarding_dir, args.suite, args.workspace)
        print(json.dumps({"selected": selected, "selection": selection}, ensure_ascii=False, indent=2))
        return 0
    result = execute(args.onboarding_dir, args.suite, args.workspace,
                     ensure_login=args.ensure_login, pilot_size=args.pilot_size)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"COMPLETED", "NO_EXECUTABLE_READY_CASES"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
