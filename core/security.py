"""Security boundaries shared by database cleanup and workspace script execution."""
from __future__ import annotations

import re
from pathlib import Path


_IDENTIFIER = re.compile(r"^[^\W\d][\w$]*$", re.UNICODE)


def validate_sql_identifier(value: str, *, label: str = "SQL identifier") -> str:
    """Accept a plain or schema-qualified SQL identifier, never SQL syntax."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    parts = value.split(".")
    if any(not _IDENTIFIER.fullmatch(part) for part in parts):
        raise ValueError(f"Unsafe {label}: {value!r}")
    return value


def validate_cleanup_targets(targets: list[dict], allowed_tables: list[str]) -> None:
    """Treat cleanup_targets as the delete allowlist and validate every identifier."""
    if targets and not allowed_tables:
        raise ValueError("cleanup_targets require non-empty allowed_tables for mutation guarding")
    for table in allowed_tables:
        validate_sql_identifier(table, label="allowed table")
    for target in targets:
        table = validate_sql_identifier(target.get("table", ""), label="cleanup table")
        if target.get("column"):
            validate_sql_identifier(target["column"], label="cleanup column")
        if target.get("key"):
            validate_sql_identifier(target["key"], label="cleanup key")
        parent = target.get("parent")
        if parent:
            parent_table = validate_sql_identifier(parent.get("table", ""), label="parent table")
            validate_sql_identifier(parent.get("key_col", ""), label="parent key column")
            validate_sql_identifier(parent.get("marker_col", ""), label="parent marker column")


def trusted_workspace_script(path: str | Path, workspace: str | Path) -> Path:
    """Resolve a Python script and require it to stay inside the selected workspace."""
    root = Path(workspace).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Workspace script escapes workspace: {candidate}") from exc
    if candidate.suffix.lower() != ".py" or not candidate.is_file():
        raise ValueError(f"Workspace script is not an existing .py file: {candidate}")
    return candidate
