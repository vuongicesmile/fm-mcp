"""HTTP entry point for the FM MCP server used by Titan Control Plane."""

from __future__ import annotations

import os

from fm_mcp.server import mcp

# Titan's MCP client is deliberately stateless and accepts JSON responses only.
# Keeping this as a separate ASGI app preserves the CLI's stdio transport for
# desktop MCP clients.
app = mcp.http_app(path="/mcp", transport="streamable-http", stateless_http=True, json_response=True)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "fm_mcp.http:app",
        host=os.environ.get("FM_MCP_HTTP_HOST", "0.0.0.0"),
        port=int(os.environ.get("FM_MCP_HTTP_PORT", "8000")),
    )
