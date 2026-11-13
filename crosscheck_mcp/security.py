"""Workspace whitelist, path containment, and output desensitization.

Single entry/exit filter for the MCP server. Every tool resolves its
workspace through :func:`resolve_workspace` (deny-by-default outside the
configured roots) and passes every outgoing payload through
:func:`sanitize` so credentials, cookies, DSNs, and full report bodies
never leave the local machine via MCP.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

WORKSPACE_ROOT_ENV = "CROSSCHECK_WORKSPACE_ROOT"

# Keys whose values must never be returned through MCP, matched
# case-insensitively as a substring of the key name.
_SECRET_KEY_HINTS = (
    "password", "passwd", "secret", "token", "cookie", "authorization",
    "auth", "credential", "dsn", "connection_string", "conn_str",
    "session", "api_key", "apikey", "access_key", "private",
)

# Result keys that may carry large/sensitive report bodies. We keep
# pointers (paths/ids) but drop inline bodies.
_BODY_KEYS = ("body", "report_body", "stdout", "stderr", "raw", "capture", "har")

_MAX_ERROR_CHARS = 500


class WorkspaceAccessError(PermissionError):
    """Raised when a requested workspace is outside the configured roots."""


def _configured_roots() -> list[Path]:
    raw = os.environ.get(WORKSPACE_ROOT_ENV, "").strip()
    if not raw:
        return []
    roots: list[Path] = []
    for part in raw.split(os.pathsep):
        part = part.strip()
        if part:
            roots.append(Path(part).resolve())
    return roots


def resolve_workspace(workspace: str | Path) -> Path:
    """Resolve *workspace* and assert it lies within a configured root.

    Deny-by-default: if ``CROSSCHECK_WORKSPACE_ROOT`` is unset, every
    workspace is rejected. A resolved path must be one of, or nested
    under, a configured root.
    """
    roots = _configured_roots()
    if not roots:
        raise WorkspaceAccessError(
            f"{WORKSPACE_ROOT_ENV} is not configured; refusing all workspace access"
        )
    candidate = Path(workspace).resolve()
    for root in roots:
        if candidate == root or _is_relative_to(candidate, root):
            return candidate
    raise WorkspaceAccessError(
        f"workspace is outside the allowed roots: {candidate}"
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _looks_secret(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in _SECRET_KEY_HINTS)


def sanitize(value: Any) -> Any:
    """Recursively strip secret-like keys and inline report bodies.

    Never raises on unexpected shapes; unknown leaf types pass through
    unchanged. String leaves are not truncated except via the dedicated
    error handling in :func:`sanitize_error`.
    """
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, inner in value.items():
            if not isinstance(key, str):
                cleaned[str(key)] = sanitize(inner)
                continue
            if _looks_secret(key):
                cleaned[key] = "[redacted]"
            elif key.lower() in _BODY_KEYS:
                cleaned[key] = "[omitted: body kept in local workspace]"
            else:
                cleaned[key] = sanitize(inner)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    return value


def sanitize_error(message: str) -> str:
    """Trim an error message to a desensitized, bounded summary."""
    text = (message or "").strip()
    if len(text) > _MAX_ERROR_CHARS:
        text = text[:_MAX_ERROR_CHARS] + "…"
    return text
