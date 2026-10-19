"""Entry point for the FM MCP Server."""

from fm_mcp.core.config import settings
from fm_mcp.server import mcp


def main() -> None:
    """Run stdio locally or stateless Streamable HTTP in a deployment."""
    if settings.mcp_transport == "stdio":
        mcp.run(transport="stdio")
        return
    if settings.mcp_transport != "streamable-http":
        raise ValueError("FM_MCP_TRANSPORT must be stdio or streamable-http")
    mcp.run(
        transport="streamable-http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        path=settings.mcp_path,
        stateless_http=True,
        json_response=True,
        show_banner=False,
    )


if __name__ == "__main__":
    main()
