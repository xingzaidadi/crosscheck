"""Machine-readable task CLI for agent hosts and future DSH integration."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.task import TaskService  # noqa: E402
from core.task.service import TaskTransitionError, TaskValidationError  # noqa: E402
from core.task.store import TaskNotFoundError  # noqa: E402


def _read_specification(path: str | Path) -> dict:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise TaskValidationError("task specification must be an object")
    return data


def _emit(payload: dict, *, pretty: bool = False) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))


def _runner(task) -> dict:
    execution = task.execution
    command = [sys.executable, str(ROOT / "run_suite.py"), "--suite", task.suite,
               "--workspace", task.workspace]
    if task.operation == "plan":
        command.append("--plan-only")
    only = task.scope.get("only") or task.scope.get("cases")
    if isinstance(only, list):
        only = ",".join(str(value) for value in only)
    if only:
        command.extend(["--only", str(only)])
    if execution.get("pilot_size") is not None:
        command.extend(["--pilot-size", str(execution["pilot_size"])])
    if execution.get("ensure_login"):
        command.append("--ensure-login")
    if execution.get("resume") is False:
        command.append("--no-resume")
    if execution.get("run_id"):
        command.extend(["--run-id", str(execution["run_id"])])
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
    log_path = Path(task.workspace) / ".crosscheck" / "tasks" / task.task_id / "execution.log"
    log_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    status = "completed" if completed.returncode == 0 else "blocked" if completed.returncode in {2, 3, 4, 6} else "failed"
    return {"status": status, "exit_code": completed.returncode, "log_path": str(log_path),
            "error": "" if completed.returncode == 0 else _last_line(completed.stdout + completed.stderr)}


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "task execution failed"


def main() -> int:
    parser = argparse.ArgumentParser(prog="crosscheck task", description="持久化 Crosscheck 测试任务")
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    sub = parser.add_subparsers(dest="action", required=True)

    create = sub.add_parser("create", help="创建任务")
    create.add_argument("--file", required=True)
    create.add_argument("--workspace")
    create.add_argument("--execute", action="store_true")

    for name in ("status", "run", "continue", "cancel", "events"):
        command = sub.add_parser(name)
        command.add_argument("task_id")
        command.add_argument("--workspace", required=True)
        if name == "cancel":
            command.add_argument("--reason", default="")

    args = parser.parse_args()
    try:
        if args.action == "create":
            specification = _read_specification(args.file)
            workspace = Path(args.workspace or specification.get("workspace") or "workspace").resolve()
            specification["workspace"] = str(workspace)
            service = TaskService(workspace)
            task = service.create(specification)
            if args.execute:
                task = service.execute(task.task_id, _runner)
        else:
            service = TaskService(args.workspace)
            if args.action == "status":
                task = service.get(args.task_id)
            elif args.action in {"run", "continue"}:
                task = service.execute(args.task_id, _runner)
            elif args.action == "cancel":
                task = service.cancel(args.task_id, args.reason)
            else:
                _emit({"schema_version": 1, "task_id": args.task_id,
                       "events": service.events(args.task_id)}, pretty=args.pretty)
                return 0
        _emit(task.to_dict(), pretty=args.pretty)
        return 0 if task.state.value in {"created", "running", "completed", "cancelled"} else 4 if task.state.value == "blocked" else 1
    except (TaskValidationError, TaskTransitionError, TaskNotFoundError, OSError, ValueError) as exc:
        _emit({"schema_version": 1, "status": "error", "error": str(exc)}, pretty=args.pretty)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
