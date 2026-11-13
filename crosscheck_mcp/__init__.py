"""Crosscheck MCP Server — generic, host-agnostic MCP wrapper over core/task.

Exposes typed, high-level tools so any MCP host (MiCo, CI, IDEs) can drive
Crosscheck without assembling CLI/shell. MiCo-specific assets live in
``integrations/mico/``; this package depends only on Crosscheck Core.

``server`` is intentionally not imported here so the package loads without
the optional ``mcp`` SDK; import :mod:`crosscheck_mcp.server` explicitly when
running the server.
"""
from __future__ import annotations

from crosscheck_mcp import schemas, security, tools

__all__ = ["schemas", "security", "tools"]
__version__ = "0.1.0"
