"""High-level tool implementations.

Every task-backed tool goes through :class:`core.task.TaskService` and,
for execution, reuses the engine's existing runner
(``scripts.task._runner``). This module never assembles shell commands and
never exposes arbitrary command execution. All outputs are desensitized by
:mod:`crosscheck_mcp.security` before returning.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from crosscheck_mcp import schemas, security

# Repo root (parent of this package) must be importable so core.task and
# scripts.task resolve regardless of the host's working directory.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _service(workspace: str):
    """Build a TaskService against a whitelisted workspace."""
    from core.task import TaskService  # imported lazily to keep import light

    resolved = security.resolve_workspace(workspace)
    return TaskService(resolved), str(resolved)


def _load_runner() -> Callable[[Any], dict]:
    """Reuse the engine's canonical suite runner; do not reimplement it."""
    from scripts.task import _runner  # type: ignore

    return _runner


def _error(message: str, *, state: str = "error") -> dict[str, Any]:
    return security.sanitize({
        "schema_version": schemas.RESULT_SCHEMA_VERSION,
        "state": state,
        "error": security.sanitize_error(message),
    })


def _ok(record_dict: dict[str, Any]) -> dict[str, Any]:
    return security.sanitize(schemas.project_task(record_dict))


# --- task-backed tools --------------------------------------------------

def task_create(arguments: dict[str, Any]) -> dict[str, Any]:
    from core.task.service import TaskValidationError

    try:
        service, workspace = _service(str(arguments["workspace"]))
    except (security.WorkspaceAccessError, KeyError) as exc:
        return _error(str(exc))

    specification = {
        "task_id": arguments.get("task_id"),
        "operation": arguments.get("operation"),
        "workspace": workspace,
        "suite": arguments.get("suite"),
        "scope": {"cases": arguments.get("cases", [])},
        "execution": {
            "pilot_size": arguments.get("pilot_size"),
            "ensure_login": arguments.get("ensure_login"),
            "resume": arguments.get("resume"),
            "run_id": arguments.get("run_id"),
        },
        "authorization": {
            "confirmed_non_production": arguments.get("confirmed_non_production"),
            "allow_write": arguments.get("allow_write"),
        },
    }
    try:
        record = service.create(specification)
        if arguments.get("execute"):
            record = service.execute(record.task_id, _load_runner())
    except TaskValidationError as exc:
        return _error(str(exc), state="validation_error")
    except Exception as exc:  # defensive: never leak a raw traceback
        return _error(str(exc))
    return _ok(record.to_dict())


def task_status(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        service, _ = _service(str(arguments["workspace"]))
        record = service.get(str(arguments["task_id"]))
    except Exception as exc:
        return _error(str(exc))
    return _ok(record.to_dict())


def task_continue(arguments: dict[str, Any]) -> dict[str, Any]:
    from core.task.service import TaskTransitionError

    try:
        service, _ = _service(str(arguments["workspace"]))
        record = service.execute(str(arguments["task_id"]), _load_runner())
    except TaskTransitionError as exc:
        return _error(str(exc), state="transition_error")
    except Exception as exc:
        return _error(str(exc))
    return _ok(record.to_dict())


def task_cancel(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        service, _ = _service(str(arguments["workspace"]))
        record = service.cancel(str(arguments["task_id"]), str(arguments.get("reason") or ""))
    except Exception as exc:
        return _error(str(exc))
    return _ok(record.to_dict())


def run_retry(arguments: dict[str, Any]) -> dict[str, Any]:
    # Retry is a re-execution of a failed/blocked task via the same path.
    return task_continue(arguments)


def report_get(arguments: dict[str, Any]) -> dict[str, Any]:
    # Return a controlled pointer only; the full report body stays local.
    try:
        service, _ = _service(str(arguments["workspace"]))
        record = service.get(str(arguments["task_id"]))
    except Exception as exc:
        return _error(str(exc))
    projected = schemas.project_task(record.to_dict())
    projected["report"] = {"log_path": (record.result or {}).get("log_path")}
    return security.sanitize(projected)


# --- reserved (phase-two) tools -----------------------------------------

def _reserved(tool_name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def _call(arguments: dict[str, Any]) -> dict[str, Any]:
        # Validate the workspace even for reserved tools so a misconfigured
        # root surfaces consistently; then return the reserved marker.
        workspace = arguments.get("workspace")
        if workspace is not None:
            try:
                security.resolve_workspace(str(workspace))
            except security.WorkspaceAccessError as exc:
                return _error(str(exc))
        return security.sanitize(schemas.reserved_result(tool_name))

    return _call


# --- dispatch table -----------------------------------------------------

DISPATCH: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "crosscheck_task_create": task_create,
    "crosscheck_task_status": task_status,
    "crosscheck_task_continue": task_continue,
    "crosscheck_task_cancel": task_cancel,
    "crosscheck_run_retry": run_retry,
    "crosscheck_report_get": report_get,
}
for _name in schemas.RESERVED_TOOLS:
    DISPATCH[_name] = _reserved(_name)


def call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call by name; unknown names return an error result."""
    handler = DISPATCH.get(tool_name)
    if handler is None:
        return _error(f"unknown tool: {tool_name}")
    return handler(dict(arguments or {}))
