"""FastMCP server initialization and tool registration."""

from fastmcp import FastMCP

from fm_mcp.tools.registry import register_tools

mcp = FastMCP("fm-mcp")
register_tools(mcp)
