"""Task lifecycle, validation, transition rules, and execution bookkeeping."""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Callable

from core.task.model import TERMINAL_STATES, TaskEvent, TaskRecord, TaskState, utc_now
from core.task.store import TaskStore


TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
SUPPORTED_OPERATIONS = {"plan", "run"}


class TaskValidationError(ValueError):
    pass


class TaskTransitionError(RuntimeError):
    pass


class TaskService:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()
        self.store = TaskStore(self.workspace)

    def create(self, specification: dict[str, Any]) -> TaskRecord:
        task_id = str(specification.get("task_id") or f"task-{uuid.uuid4().hex[:12]}")
        if not TASK_ID_PATTERN.fullmatch(task_id):
            raise TaskValidationError("task_id must be a safe 1-96 character identifier")
        operation = str(specification.get("operation") or "run").lower()
        if operation not in SUPPORTED_OPERATIONS:
            raise TaskValidationError(f"unsupported operation: {operation}")
        configured_workspace = Path(specification.get("workspace") or self.workspace).resolve()
        if configured_workspace != self.workspace:
            raise TaskValidationError("task workspace must match the selected task store workspace")
        suite = self._resolve_suite(specification.get("suite"))
        if (self.store.task_dir(task_id) / "task.json").exists():
            raise TaskValidationError(f"task already exists: {task_id}")
        task = TaskRecord(
            task_id=task_id,
            operation=operation,
            workspace=str(self.workspace),
            suite=str(suite),
            scope=dict(specification.get("scope") or {}),
            execution=dict(specification.get("execution") or {}),
            authorization=dict(specification.get("authorization") or {}),
        )
        self.store.save(task)
        self._event(task, "task.created", {"operation": operation, "suite": str(suite)})
        return task

    def get(self, task_id: str) -> TaskRecord:
        return self.store.load(task_id)

    def cancel(self, task_id: str, reason: str = "") -> TaskRecord:
        task = self.get(task_id)
        if task.state in TERMINAL_STATES:
            raise TaskTransitionError(f"cannot cancel task in state {task.state.value}")
        task.state = TaskState.CANCELLED
        task.error = reason
        task.updated_at = utc_now()
        self.store.save(task)
        self._event(task, "task.cancelled", {"reason": reason})
        return task

    def execute(self, task_id: str, runner: Callable[[TaskRecord], dict[str, Any]]) -> TaskRecord:
        task = self.get(task_id)
        if task.state not in {TaskState.CREATED, TaskState.BLOCKED, TaskState.FAILED}:
            raise TaskTransitionError(f"cannot execute task in state {task.state.value}")
        task.state = TaskState.RUNNING
        task.attempts += 1
        task.error = ""
        task.updated_at = utc_now()
        self.store.save(task)
        self._event(task, "task.started", {"attempt": task.attempts})
        try:
            outcome = dict(runner(task) or {})
        except Exception as exc:
            task.state = TaskState.FAILED
            task.error = str(exc)
            task.updated_at = utc_now()
            self.store.save(task)
            self._event(task, "task.failed", {"error": task.error})
            return task
        task.result = outcome
        task.progress = dict(outcome.get("progress") or task.progress)
        status = str(outcome.get("status") or "completed")
        if status == "blocked":
            task.state = TaskState.BLOCKED
        elif status == "completed":
            task.state = TaskState.COMPLETED
        else:
            task.state = TaskState.FAILED
        task.error = str(outcome.get("error") or "")
        task.updated_at = utc_now()
        self.store.save(task)
        self._event(task, f"task.{task.state.value}", {"result": outcome})
        return task

    def events(self, task_id: str) -> list[dict[str, Any]]:
        return self.store.events(task_id)

    def _resolve_suite(self, value: Any) -> Path:
        if not value:
            raise TaskValidationError("suite is required")
        suite = Path(str(value))
        if not suite.is_absolute():
            suite = self.workspace / suite
        suite = suite.resolve()
        try:
            suite.relative_to(self.workspace)
        except ValueError as exc:
            raise TaskValidationError("suite must stay inside the selected workspace") from exc
        if not suite.is_dir() or not (suite / "suite.yaml").is_file():
            raise TaskValidationError(f"canonical suite not found: {suite}")
        return suite

    def _event(self, task: TaskRecord, event_type: str, payload: dict[str, Any]) -> None:
        event = TaskEvent(
            event_id=f"evt-{uuid.uuid4().hex[:16]}",
            task_id=task.task_id,
            event_type=event_type,
            state=task.state.value,
            payload=payload,
        )
        self.store.append_event(event)
