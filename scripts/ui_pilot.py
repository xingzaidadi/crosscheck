"""High-level UI-only pilot entry point.

Discovers an existing canonical suite, reuses configured sessions, selects a
small read-only UI set, and delegates execution to the canonical runner.
"""
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

from core.suite_context import SuiteContext  # noqa: E402
from core.suite_dsl import load_suite  # noqa: E402
from core.suite_execution import build_execution_plan  # noqa: E402
from core.workspace import set_workspace  # noqa: E402


RISKY_WORDS = ("提交", "保存", "删除", "新建", "暂存", "上传", "导入", "导出",
               "审批", "驳回", "受理", "关闭", "创建", "编辑")


def discover_suite(workspace: str | Path, *, suite: str | Path | None = None,
                   cases: str | Path | None = None) -> Path:
    workspace = Path(workspace).resolve()
    if suite:
        candidate = Path(suite).resolve()
        if not (candidate / "suite.yaml").is_file():
            raise FileNotFoundError(f"suite.yaml not found: {candidate}")
        return candidate
    suite_dirs = [path for path in (workspace / "suites").iterdir()
                  if path.is_dir() and not path.name.startswith("_")
                  and (path / "suite.yaml").is_file()]
    if not suite_dirs:
        raise FileNotFoundError(f"no canonical suite found under {workspace / 'suites'}")
    if cases:
        case_name = Path(cases).name
        matching = []
        for path in suite_dirs:
            try:
                source = json.loads("{}")
                import yaml
                source = yaml.safe_load((path / "suite.yaml").read_text(encoding="utf-8")) or {}
                if Path(str((source.get("source") or {}).get("file") or "")).name == case_name:
                    matching.append(path)
            except Exception:
                continue
        if matching:
            return max(matching, key=lambda path: path.stat().st_mtime)
    return max(suite_dirs, key=lambda path: path.stat().st_mtime)


def _is_read_only(spec) -> tuple[bool, str]:
    title = str(getattr(spec, "title", "") or "")
    ui = getattr(spec, "ui", None) or {}
    if getattr(spec, "mode", "") != "ui":
        return False, "not a UI execution"
    if ui.get("page_model"):
        return False, "UI write model present"
    if any(word in title for word in RISKY_WORDS):
        return False, "title indicates write or workflow action"
    return True, "read-only UI heuristic"


def select_pilot(specs: list, lifecycle: dict[str, Any], *, only: str | None = None,
                  pilot_size: int = 3) -> tuple[list, list[dict[str, str]]]:
    wanted = {item.strip() for item in (only or "").split(",") if item.strip()}
    rows = {row.get("source_case_key"): row for row in lifecycle.get("cases", [])}
    selected = []
    excluded = []
    for spec in specs:
        key = str((spec.raw or {}).get("canonical_case_key") or "")
        if wanted and key not in wanted and spec.case_id not in wanted:
            continue
        ok, reason = _is_read_only(spec)
        if ok:
            selected.append(spec)
        else:
            excluded.append({"case_id": key or spec.case_id, "reason": reason})
    if not wanted:
        selected.sort(key=lambda spec: (str(getattr(spec, "level", "P9")),
                                        str((spec.raw or {}).get("canonical_case_key") or spec.case_id)))
        overflow = selected[pilot_size:]
        selected = selected[:pilot_size]
        excluded.extend({"case_id": str((spec.raw or {}).get("canonical_case_key") or spec.case_id),
                         "reason": "pilot limit"} for spec in overflow)
    return selected, excluded


def auto_progress_allowed(selected: list, excluded: list[dict[str, str]]) -> dict[str, Any]:
    """Return a conservative expansion decision after the pilot selection stage.

    Only a non-empty, read-only selection with no binding/readiness exclusions can
    expand automatically.  Business FAIL/INCONCLUSIVE remains a result, not a
    reason to silently widen scope.
    """
    hard_exclusions = [row for row in excluded if row.get("reason") != "pilot limit"]
    return {
        "allowed": bool(selected) and not hard_exclusions,
        "selected_count": len(selected),
        "hard_exclusions": hard_exclusions,
        "reason": "pilot selection is safe" if selected and not hard_exclusions
        else "pilot has no safe execution set or has readiness exclusions",
    }


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    set_workspace(workspace)
    suite_dir = discover_suite(workspace, suite=args.suite, cases=args.cases)
    suite, cases = load_suite(suite_dir)
    context = SuiteContext.create(suite_dir, workspace)
    specs, lifecycle = build_execution_plan(suite, cases, context, suite_dir, phase="ui")
    selected, excluded = select_pilot(specs, lifecycle, only=args.only, pilot_size=args.pilot_size)
    expansion = auto_progress_allowed(selected, excluded)
    run_id = args.run_id or f"ui_pilot_{time.strftime('%Y%m%d_%H%M%S')}"
    report_dir = suite_dir / "reports" / "runs" / run_id
    result: dict[str, Any] = {
        "schema_version": 1,
        "mode": "ui-only",
        "phase": "ui",
        "suite": str(suite_dir),
        "workspace": str(workspace),
        "session_policy": "reuse_existing_then_credential_refresh",
        "selected": [str((spec.raw or {}).get("canonical_case_key") or spec.case_id) for spec in selected],
        "excluded": excluded,
        "auto_progress": expansion,
        "execution": None,
    }
    if not selected:
        result["status"] = "NO_READ_ONLY_UI_READY_CASES"
    elif args.plan_only:
        result["status"] = "READY_TO_RUN"
    else:
        command = [sys.executable, str(ROOT / "run_suite.py"), "--suite", str(suite_dir),
                   "--workspace", str(workspace), "--only", ",".join(result["selected"]),
                   "--pilot-size", str(args.pilot_size), "--run-id", run_id, "--ui-first"]
        if not args.no_session_refresh:
            command.append("--ensure-login")
        if args.no_resume:
            command.append("--no-resume")
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
        summary_path = report_dir / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
        result["status"] = "COMPLETED" if completed.returncode == 0 else "FAILED_OR_BLOCKED"
        result["execution"] = {"run_id": run_id, "exit_code": completed.returncode,
                                "command": command, "summary": summary,
                                "report": str(report_dir / "report.html") if (report_dir / "report.html").exists() else "",
                                "stdout": completed.stdout, "stderr": completed.stderr}
    _write_json(suite_dir / "reports" / "ui_pilot_latest.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="自动发现并执行低风险 UI-only Pilot")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--suite")
    parser.add_argument("--cases", help="用于匹配 suite source 的原始用例文件")
    parser.add_argument("--only", help="逗号分隔的 case key；指定后不做自动扩展")
    parser.add_argument("--pilot-size", type=int, default=3)
    parser.add_argument("--run-id")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--no-session-refresh", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"COMPLETED", "READY_TO_RUN"} else 4
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"schema_version": 1, "status": "ERROR", "error": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
