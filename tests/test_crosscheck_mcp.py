"""Contract tests for the crosscheck_mcp server (no MCP SDK required).

These exercise security (workspace whitelist + desensitization), the
task-result projection, and the task-backed/reserved tool dispatch
without running a real suite.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crosscheck_mcp import schemas, security, tools  # noqa: E402


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    suite = ws / "suites" / "demo"
    suite.mkdir(parents=True)
    (suite / "suite.yaml").write_text("id: demo\n", encoding="utf-8")
    monkeypatch.setenv(security.WORKSPACE_ROOT_ENV, str(tmp_path))
    return ws


# --- security -----------------------------------------------------------

def test_resolve_workspace_accepts_inside_root(workspace):
    assert security.resolve_workspace(workspace) == workspace.resolve()


def test_resolve_workspace_rejects_outside_root(tmp_path, monkeypatch):
    monkeypatch.setenv(security.WORKSPACE_ROOT_ENV, str(tmp_path / "allowed"))
    (tmp_path / "allowed").mkdir()
    with pytest.raises(security.WorkspaceAccessError):
        security.resolve_workspace(tmp_path / "elsewhere")


def test_resolve_workspace_denies_when_root_unset(tmp_path, monkeypatch):
    monkeypatch.delenv(security.WORKSPACE_ROOT_ENV, raising=False)
    with pytest.raises(security.WorkspaceAccessError):
        security.resolve_workspace(tmp_path)


def test_sanitize_redacts_secrets_and_omits_bodies():
    payload = {
        "password": "p",
        "db_dsn": "mysql://u:p@h/db",
        "cookie": "x",
        "nested": {"api_key": "k", "state": "completed", "report_body": "huge"},
        "safe": "keep",
    }
    cleaned = security.sanitize(payload)
    assert cleaned["password"] == "[redacted]"
    assert cleaned["db_dsn"] == "[redacted]"
    assert cleaned["cookie"] == "[redacted]"
    assert cleaned["nested"]["api_key"] == "[redacted]"
    assert cleaned["nested"]["report_body"].startswith("[omitted")
    assert cleaned["nested"]["state"] == "completed"
    assert cleaned["safe"] == "keep"


# --- schemas ------------------------------------------------------------

def test_project_task_shape():
    projected = schemas.project_task({
        "schema_version": 1, "task_id": "t1", "operation": "plan",
        "suite": "suites/demo", "state": "completed", "progress": {"total": 3},
        "result": {"status": "completed", "exit_code": 0, "log_path": "x"},
    })
    for key in ("schema_version", "task_id", "state", "progress", "blockers", "stage"):
        assert key in projected
    assert projected["blockers"] == []


def test_project_task_blocked_populates_blockers():
    projected = schemas.project_task({
        "task_id": "t2", "operation": "run", "state": "blocked",
        "result": {"status": "blocked", "error": "没有可执行的 approved canonical case"},
    })
    assert projected["state"] == "blocked"
    assert projected["blockers"] and projected["blockers"][0]["type"] == "execution"


def test_reserved_tools_cover_the_six_non_task_tools():
    assert schemas.RESERVED_TOOLS == {
        "crosscheck_project_init", "crosscheck_project_inspect",
        "crosscheck_approval_decide", "crosscheck_cleanup_run",
    }


# --- tool dispatch ------------------------------------------------------

def test_task_create_without_execute(workspace):
    result = tools.call("crosscheck_task_create", {
        "workspace": str(workspace), "suite": "suites/demo", "operation": "plan",
        "task_id": "mcp-t-001",
    })
    assert result["state"] == "created"
    assert result["task_id"] == "mcp-t-001"
    assert result["schema_version"] == 1


def test_task_status_and_cancel(workspace):
    tools.call("crosscheck_task_create", {
        "workspace": str(workspace), "suite": "suites/demo", "operation": "plan",
        "task_id": "mcp-t-002",
    })
    status = tools.call("crosscheck_task_status", {
        "workspace": str(workspace), "task_id": "mcp-t-002"})
    assert status["state"] == "created"
    cancelled = tools.call("crosscheck_task_cancel", {
        "workspace": str(workspace), "task_id": "mcp-t-002", "reason": "test"})
    assert cancelled["state"] == "cancelled"


def test_invalid_operation_is_validation_error(workspace):
    result = tools.call("crosscheck_task_create", {
        "workspace": str(workspace), "suite": "suites/demo", "operation": "delete",
    })
    assert result["state"] == "validation_error"


def test_workspace_outside_root_is_error(tmp_path, monkeypatch):
    monkeypatch.setenv(security.WORKSPACE_ROOT_ENV, str(tmp_path / "allowed"))
    (tmp_path / "allowed").mkdir()
    result = tools.call("crosscheck_task_status", {
        "workspace": str(tmp_path / "evil"), "task_id": "x"})
    assert result["state"] == "error"


def test_reserved_tool_returns_reserved(workspace):
    result = tools.call("crosscheck_cleanup_run", {
        "workspace": str(workspace), "task_id": "x"})
    assert result["state"] == "reserved"


def test_unknown_tool_returns_error(workspace):
    result = tools.call("crosscheck_nope", {"workspace": str(workspace)})
    assert result["state"] == "error"
