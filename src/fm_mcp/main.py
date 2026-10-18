"""Entry point for the FM MCP Server."""

from fm_mcp.server import mcp


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
