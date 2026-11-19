"""Turn readiness gaps into deterministic, assignable remediation tasks."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _task_id(case_id: str, task_type: str) -> str:
    value = f"{case_id}:{task_type}".encode("utf-8")
    return "uitask-" + hashlib.sha256(value).hexdigest()[:12]


def build_task_queue(readiness: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for row in readiness.get("cases") or []:
        status = str(row.get("status") or "")
        if status == "UI_EXECUTABLE":
            continue
        reason = str(row.get("reason") or "")
        case_id = str(row.get("case_id") or "unknown")
        if status == "UI_BLOCKED":
            task_type, owner, action = "business_clarification", "business", "resolve_rule"
        elif "fixture" in reason.lower() or "data" in reason.lower() or "数据" in reason:
            task_type, owner, action = "fixture", "test-data", "define_fixture"
        elif "oracle" in reason.lower() or "断言" in reason:
            task_type, owner, action = "oracle", "qa", "review_oracle"
        elif "entry" in reason.lower() or "页面入口" in reason:
            task_type, owner, action = "page_exploration", "automation", "explore_page"
        else:
            task_type, owner, action = "binding_replay", "automation", "explore_and_replay"
        tasks.append({
            "task_id": _task_id(case_id, task_type), "case_id": case_id,
            "title": row.get("title", ""), "type": task_type, "owner": owner,
            "action": action, "status": "OPEN", "reason": reason,
            "dependencies": [],
        })
    return tasks


def queue_summary(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    for task in tasks:
        by_type[task["type"]] = by_type.get(task["type"], 0) + 1
    return {"total": len(tasks), "open": sum(t.get("status") == "OPEN" for t in tasks),
            "by_type": by_type, "fingerprint": hashlib.sha256(
                json.dumps(tasks, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()}

