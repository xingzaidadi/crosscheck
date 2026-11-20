"""Persist and resume the analyze-review-recheck-run onboarding workflow."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.framework import fingerprint, load_document, load_suite_assets  # noqa: E402


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _flow_id(cases: Path, requirements: Path | None, profile: Path | None,
             suite: Path | None) -> str:
    value = {
        "cases": load_document(cases),
        "requirements": load_document(requirements) if requirements else None,
        "profile": load_document(profile) if profile else {},
        "suite_asset_fingerprint": load_suite_assets(suite).get("fingerprint", "") if suite else "",
    }
    return f"flow-{fingerprint(value)[:16]}"


def _run_onboarding(inputs: dict[str, str], resolutions: Path | None, execute: bool,
                    ensure_login: bool, pilot_size: int) -> dict[str, Any]:
    command = [sys.executable, str(ROOT / "run_onboard.py"), "onboard",
               "--cases", inputs["cases"], "--workspace", inputs["workspace"]]
    for option in ("requirements", "profile"):
        if inputs.get(option):
            command.extend([f"--{option}", inputs[option]])
    if inputs.get("suite"):
        command.extend(["--suite-assets", inputs["suite"]])
    if resolutions:
        command.extend(["--resolutions", str(resolutions)])
    if execute:
        command.extend(["--execute-ready", "--pilot-size", str(pilot_size)])
        if ensure_login:
            command.append("--ensure-login")
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "onboarding failed"
        raise RuntimeError(detail)
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"onboarding returned invalid JSON: {completed.stdout[-500:]}") from exc
    result["command"] = command
    return result


def _render_markdown(report: dict[str, Any]) -> str:
    execution = report.get("execution") or {}
    summary = execution.get("summary") or {}
    lines = [
        "# Crosscheck 统一闭环报告",
        "",
        f"- Flow ID: `{report['flow_id']}`",
        f"- 状态: **{report['status']}**",
        f"- 用例总数: {report['analysis']['case_count']}",
        f"- READY: {report['analysis']['ready_count']}",
        f"- 待补充缺口: {report['analysis']['gap_count']}",
        f"- Onboarding: `{report['analysis']['onboarding_output']}`",
        f"- 缺口模板: `{report['analysis']['resolution_template']}`",
        "",
        "## 执行结果",
        "",
    ]
    if execution:
        lines.extend([
            f"- 状态: {execution.get('status', 'UNKNOWN')}",
            f"- 运行 ID: `{execution.get('run_id', '')}`",
            f"- 总数/通过/失败/跳过: {summary.get('total', 0)}/{summary.get('pass', 0)}/"
            f"{summary.get('fail', 0)}/{summary.get('skip', 0)}",
            f"- 执行报告: `{execution.get('report', '')}`",
        ])
    else:
        lines.append("- 尚未执行；补充并审批缺口模板后使用 `crosscheck flow --continue <flow-dir> --resolutions <file>`。")
    if report.get("remaining_gaps"):
        lines.extend(["", "## 未结缺口", ""])
        for item in report["remaining_gaps"]:
            lines.append(f"- `{item.get('gap_id')}` {item.get('type')}: {item.get('reason')}")
    return "\n".join(lines) + "\n"


def _persist(flow_dir: Path, state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    onboarding = Path(result["output"])
    gaps = _read_json(onboarding / "gap_report.json")
    resolution_audit = _read_json(onboarding / "resolution_audit.json")
    execution = result.get("execution")
    if execution and execution.get("status") == "COMPLETED":
        status = "COMPLETED" if not gaps.get("gaps") else "COMPLETED_WITH_GAPS"
    elif execution:
        status = execution.get("status", "FAILED_OR_BLOCKED")
    elif not state["inputs"].get("suite"):
        status = "READY_NO_EXECUTION_SUITE"
    elif gaps.get("gaps"):
        status = "WAITING_FOR_INPUT"
    elif state["inputs"].get("suite"):
        status = "READY_TO_EXECUTE"
    else:
        status = "READY_NO_EXECUTION_SUITE"
    report = {
        "schema_version": 1,
        "flow_id": state["flow_id"],
        "status": status,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "inputs": state["inputs"],
        "analysis": {
            "onboarding_id": result["onboarding_id"],
            "onboarding_output": str(onboarding),
            "case_count": result["case_count"],
            "ready_count": result["ready_count"],
            "gap_count": result["gap_count"],
            "resolution_template": str(onboarding / "gap_resolutions.template.yaml"),
            "resolution_audit": resolution_audit,
        },
        "remaining_gaps": gaps.get("gaps", []),
        "execution": execution,
    }
    report_json = flow_dir / "unified_report.json"
    report_md = flow_dir / "unified_report.md"
    _write_json(report_json, report)
    report_md.write_text(_render_markdown(report), encoding="utf-8")
    state.update({"status": status, "updated_at": report["generated_at"],
                  "current_onboarding": str(onboarding), "unified_report": str(report_json),
                  "resolution_template": report["analysis"]["resolution_template"]})
    state.setdefault("history", []).append({"at": report["generated_at"], "status": status,
                                             "onboarding_id": result["onboarding_id"],
                                             "ready_count": result["ready_count"],
                                             "gap_count": result["gap_count"],
                                             "executed": execution is not None})
    _write_json(flow_dir / "state.json", state)
    return {**report, "flow_dir": str(flow_dir), "unified_report": str(report_json),
            "unified_report_markdown": str(report_md)}


def start(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    cases = Path(args.cases).resolve()
    requirements = Path(args.requirements).resolve() if args.requirements else None
    profile = Path(args.profile).resolve() if args.profile else None
    suite = Path(args.suite).resolve() if args.suite else None
    flow_id = _flow_id(cases, requirements, profile, suite)
    flow_dir = workspace / ".crosscheck" / "flows" / flow_id
    inputs = {"workspace": str(workspace), "cases": str(cases),
              "requirements": str(requirements) if requirements else "",
              "profile": str(profile) if profile else "", "suite": str(suite) if suite else ""}
    state = {"schema_version": 1, "flow_id": flow_id, "input_fingerprint": flow_id.removeprefix("flow-"),
             "status": "ANALYZING",
             "created_at": time.strftime("%Y-%m-%d %H:%M:%S"), "inputs": inputs, "history": []}
    flow_dir.mkdir(parents=True, exist_ok=True)
    resolution = Path(args.resolutions).resolve() if args.resolutions else None
    result = _run_onboarding(inputs, resolution, False, args.ensure_login, args.pilot_size)
    if suite and (args.execute_without_gaps or not _read_json(Path(result["output"]) / "gap_report.json").get("gaps")):
        result = _run_onboarding(inputs, resolution, True, args.ensure_login, args.pilot_size)
    return _persist(flow_dir, state, result)


def resume(args: argparse.Namespace) -> dict[str, Any]:
    flow_dir = Path(args.continue_flow).resolve()
    state = _read_json(flow_dir / "state.json")
    inputs = state.get("inputs") or {}
    required = [inputs.get("cases"), inputs.get("workspace")]
    if not all(required):
        raise ValueError("flow state is missing required input paths")
    current_flow_id = _flow_id(Path(inputs["cases"]),
                               Path(inputs["requirements"]) if inputs.get("requirements") else None,
                               Path(inputs["profile"]) if inputs.get("profile") else None,
                               Path(inputs["suite"]) if inputs.get("suite") else None)
    if current_flow_id != state.get("flow_id"):
        raise ValueError("flow inputs changed; start a new flow instead of resuming stale state")
    resolution = Path(args.resolutions).resolve() if args.resolutions else Path(state["resolution_template"])
    if not resolution.exists():
        raise ValueError(f"resolution file not found: {resolution}")
    execute = bool(state["inputs"].get("suite"))
    result = _run_onboarding(state["inputs"], resolution, execute, args.ensure_login, args.pilot_size)
    return _persist(flow_dir, state, result)


def main() -> int:
    parser = argparse.ArgumentParser(description="统一分析、补缺、复核、READY 执行和报告闭环")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--cases")
    mode.add_argument("--continue", dest="continue_flow")
    parser.add_argument("--requirements")
    parser.add_argument("--profile")
    parser.add_argument("--suite", help="approved canonical suite directory")
    parser.add_argument("--resolutions")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--pilot-size", type=int, default=3)
    parser.add_argument("--ensure-login", action="store_true")
    parser.add_argument("--execute-without-gaps", action="store_true",
                        help="首轮没有待确认缺口时直接执行 READY")
    args = parser.parse_args()
    try:
        report = resume(args) if args.continue_flow else start(args)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report["status"] in {"COMPLETED", "READY_NO_EXECUTION_SUITE", "READY_TO_EXECUTE",
                                 "WAITING_FOR_INPUT", "COMPLETED_WITH_GAPS"}:
            return 0
        return 4 if report["status"] in {"NO_EXECUTABLE_READY_CASES"} else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"schema_version": 1, "status": "ERROR", "error": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
