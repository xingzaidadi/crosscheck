"""Filesystem task store with atomic records and append-only events."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.task.model import TaskEvent, TaskRecord


class TaskNotFoundError(FileNotFoundError):
    pass


class TaskStore:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()
        self.root = self.workspace / ".crosscheck" / "tasks"
        self.root.mkdir(parents=True, exist_ok=True)

    def task_dir(self, task_id: str) -> Path:
        return self.root / task_id

    def save(self, task: TaskRecord) -> Path:
        directory = self.task_dir(task.task_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "task.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(task.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        return path

    def load(self, task_id: str) -> TaskRecord:
        path = self.task_dir(task_id) / "task.json"
        if not path.is_file():
            raise TaskNotFoundError(f"task not found: {task_id}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"task record is unreadable: {task_id}") from exc
        return TaskRecord.from_dict(data)

    def append_event(self, event: TaskEvent) -> Path:
        directory = self.task_dir(event.task_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return path

    def events(self, task_id: str) -> list[dict[str, Any]]:
        self.load(task_id)
        path = self.task_dir(task_id) / "events.jsonl"
        if not path.is_file():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events
