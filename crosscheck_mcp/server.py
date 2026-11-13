"""MCP server lifecycle and tool registration (stdio transport).

Built on the standard MCP Python SDK. The SDK is imported lazily inside
:func:`build_server` so the rest of the package (tools/schemas/security)
stays importable and testable without the ``mcp`` extra installed.

Run with::

    pip install "crosscheck-agent[mcp]"
    python -m crosscheck_mcp
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from crosscheck_mcp import schemas, tools

SERVER_NAME = "crosscheck"


def _require_mcp():
    try:
        import mcp.types as types  # noqa: F401
        from mcp.server import Server  # noqa: F401
        from mcp.server.stdio import stdio_server  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise SystemExit(
            "缺少 MCP SDK。请安装可选依赖:pip install \"crosscheck-agent[mcp]\""
        ) from exc
    return types, Server, stdio_server


def build_server():
    """Construct and wire the MCP Server instance."""
    types, Server, _ = _require_mcp()
    app = Server(SERVER_NAME)

    @app.list_tools()
    async def list_tools() -> list[Any]:
        return [
            types.Tool(
                name=name,
                description=schemas.TOOL_DESCRIPTIONS.get(name, name),
                inputSchema=schemas.INPUT_SCHEMAS[name],
            )
            for name in schemas.INPUT_SCHEMAS
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        result = tools.call(name, arguments or {})
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    return app


async def _serve() -> None:
    _, _, stdio_server = _require_mcp()
    app = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
