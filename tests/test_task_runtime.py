"""Persistent tasks enforce safe paths, transitions, events, and recovery."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.task import TaskService, TaskState  # noqa: E402
from core.task.service import TaskTransitionError, TaskValidationError  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory) / "workspace"
        suite = workspace / "suites" / "demo"
        suite.mkdir(parents=True)
        (suite / "suite.yaml").write_text("suite_id: demo\n", encoding="utf-8")
        service = TaskService(workspace)
        task = service.create({"task_id": "demo-task", "operation": "plan",
                               "workspace": str(workspace), "suite": "suites/demo"})
        assert task.state is TaskState.CREATED
        assert len(service.events(task.task_id)) == 1
        completed = service.execute(task.task_id, lambda _: {"status": "completed", "progress": {"total": 1}})
        assert completed.state is TaskState.COMPLETED and completed.progress["total"] == 1
        try:
            service.cancel(task.task_id)
        except TaskTransitionError:
            pass
        else:
            raise AssertionError("completed tasks cannot be cancelled")
        try:
            service.create({"operation": "run", "workspace": str(workspace), "suite": "../outside"})
        except TaskValidationError:
            pass
        else:
            raise AssertionError("suite path escape must be rejected")

        specification = workspace / "task.yaml"
        specification.write_text(yaml.safe_dump({"task_id": "cli-task", "operation": "plan",
                                                  "workspace": str(workspace), "suite": "suites/demo"}), encoding="utf-8")
        result = subprocess.run([sys.executable, "crosscheck_cli.py", "task", "create", "--file",
                                 str(specification)], cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout.strip())
        assert payload["task_id"] == "cli-task" and payload["state"] == "created"
        status = subprocess.run([sys.executable, "crosscheck_cli.py", "task", "status", "cli-task",
                                 "--workspace", str(workspace)], cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        assert status.returncode == 0
        assert json.loads(status.stdout.strip())["state"] == "created"
    print("task runtime passed")


if __name__ == "__main__":
    main()
