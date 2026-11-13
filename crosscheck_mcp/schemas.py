"""Tool input schemas and the shared task-result projection.

Kept in sync with ``integrations/mico/contracts/task-result.schema.json``.
The projection (:func:`project_task`) is the single shape every
task-backed tool returns, carrying ``schema_version``, ``task_id``,
``state``, ``progress``, and ``blockers``.
"""
from __future__ import annotations

from typing import Any

# Mirrors core.task.model.TASK_SCHEMA_VERSION; re-declared here so schema
# consumers do not need to import the runtime.
RESULT_SCHEMA_VERSION = 1

_WORKSPACE_PROP = {
    "type": "string",
    "description": "任务 workspace 绝对路径；必须位于 CROSSCHECK_WORKSPACE_ROOT 之内。",
}
_TASK_ID_PROP = {
    "type": "string",
    "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$",
    "description": "1-96 字符安全标识符,在该 workspace 内唯一。",
}

# inputSchema per tool. Tools not backed by core/task keep a minimal
# schema and return a structured `reserved` result at call time.
INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "crosscheck_project_init": {
        "type": "object",
        "properties": {"workspace": _WORKSPACE_PROP},
        "required": ["workspace"],
    },
    "crosscheck_project_inspect": {
        "type": "object",
        "properties": {"workspace": _WORKSPACE_PROP, "suite": {"type": "string"}},
        "required": ["workspace", "suite"],
    },
    "crosscheck_task_create": {
        "type": "object",
        "properties": {
            "workspace": _WORKSPACE_PROP,
            "suite": {"type": "string", "description": "workspace 内 canonical 套件目录(含 suite.yaml)。"},
            "operation": {"type": "string", "enum": ["plan", "run"]},
            "task_id": _TASK_ID_PROP,
            "pilot_size": {"type": "integer", "minimum": 0},
            "ensure_login": {"type": "boolean"},
            "resume": {"type": "boolean"},
            "run_id": {"type": "string"},
            "cases": {"type": "array", "items": {"type": "string"}},
            "confirmed_non_production": {"type": "boolean"},
            "allow_write": {"type": "boolean"},
            "execute": {"type": "boolean", "description": "true 则创建后立即执行。"},
        },
        "required": ["workspace", "suite", "operation"],
    },
    "crosscheck_task_status": {
        "type": "object",
        "properties": {"workspace": _WORKSPACE_PROP, "task_id": _TASK_ID_PROP},
        "required": ["workspace", "task_id"],
    },
    "crosscheck_task_continue": {
        "type": "object",
        "properties": {"workspace": _WORKSPACE_PROP, "task_id": _TASK_ID_PROP},
        "required": ["workspace", "task_id"],
    },
    "crosscheck_task_cancel": {
        "type": "object",
        "properties": {
            "workspace": _WORKSPACE_PROP,
            "task_id": _TASK_ID_PROP,
            "reason": {"type": "string"},
        },
        "required": ["workspace", "task_id"],
    },
    "crosscheck_approval_decide": {
        "type": "object",
        "properties": {
            "workspace": _WORKSPACE_PROP,
            "task_id": _TASK_ID_PROP,
            "decision": {"type": "string", "enum": ["approve", "reject"]},
        },
        "required": ["workspace", "task_id", "decision"],
    },
    "crosscheck_run_retry": {
        "type": "object",
        "properties": {"workspace": _WORKSPACE_PROP, "task_id": _TASK_ID_PROP},
        "required": ["workspace", "task_id"],
    },
    "crosscheck_cleanup_run": {
        "type": "object",
        "properties": {"workspace": _WORKSPACE_PROP, "task_id": _TASK_ID_PROP},
        "required": ["workspace", "task_id"],
    },
    "crosscheck_report_get": {
        "type": "object",
        "properties": {"workspace": _WORKSPACE_PROP, "task_id": _TASK_ID_PROP},
        "required": ["workspace", "task_id"],
    },
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "crosscheck_project_init": "初始化 Crosscheck 项目 workspace(阶段二保留,未实现)。",
    "crosscheck_project_inspect": "检查套件就绪度与结构评分(阶段二保留,未实现)。",
    "crosscheck_task_create": "创建一个持久化 Crosscheck 测试任务,可选立即执行。",
    "crosscheck_task_status": "查询任务当前状态与进度。",
    "crosscheck_task_continue": "继续执行已创建/阻塞/失败的任务。",
    "crosscheck_task_cancel": "取消一个非终态任务。",
    "crosscheck_approval_decide": "对用例审批做决定(阶段二保留,人工审批不经 MCP 绕过)。",
    "crosscheck_run_retry": "重跑一个失败或阻塞的任务。",
    "crosscheck_cleanup_run": "触发运行后清理(阶段二保留,未实现)。",
    "crosscheck_report_get": "获取任务报告的受控指针(不返回完整报告正文)。",
}

# Tools backed by core.task; everything else returns a `reserved` result.
TASK_BACKED_TOOLS = frozenset({
    "crosscheck_task_create",
    "crosscheck_task_status",
    "crosscheck_task_continue",
    "crosscheck_task_cancel",
    "crosscheck_run_retry",
    "crosscheck_report_get",
})

RESERVED_TOOLS = frozenset(INPUT_SCHEMAS) - TASK_BACKED_TOOLS


def _stage_for(operation: str, state: str) -> str:
    if state in {"completed", "blocked", "failed", "cancelled"}:
        return state
    return "plan" if operation == "plan" else "run"


def _blockers_for(record: dict[str, Any]) -> list[dict[str, Any]]:
    if record.get("state") != "blocked":
        return []
    reason = (record.get("result") or {}).get("error") or record.get("error") or "blocked"
    return [{"type": "execution", "reason": reason, "cases": []}]


def project_task(record: dict[str, Any]) -> dict[str, Any]:
    """Project a TaskRecord dict into the stable MCP result shape.

    Carries the fields the host contract requires and leaves
    desensitization to :mod:`crosscheck_mcp.security`.
    """
    operation = record.get("operation", "")
    state = record.get("state", "")
    result = record.get("result") or {}
    return {
        "schema_version": record.get("schema_version", RESULT_SCHEMA_VERSION),
        "task_id": record.get("task_id"),
        "operation": operation,
        "suite": record.get("suite"),
        "state": state,
        "stage": _stage_for(operation, state),
        "progress": record.get("progress") or {},
        "blockers": _blockers_for(record),
        "attempts": record.get("attempts", 0),
        "result": {
            "status": result.get("status"),
            "exit_code": result.get("exit_code"),
            "log_path": result.get("log_path"),
        },
    }


def reserved_result(tool_name: str) -> dict[str, Any]:
    """Structured result for tools not yet backed by core/task."""
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "tool": tool_name,
        "state": "reserved",
        "blockers": [{
            "type": "not_implemented",
            "reason": f"{tool_name} 为阶段二保留工具,当前未由 core/task 实现。",
            "cases": [],
        }],
    }
