"""Register the supported Workflow Automation MCP tools."""

from fastmcp import FastMCP

from fm_mcp.tools.approval import TOOLS as APPROVAL_TOOLS
from fm_mcp.tools.collector import TOOLS as COLLECTOR_TOOLS
from fm_mcp.tools.notification import TOOLS as NOTIFICATION_TOOLS
from fm_mcp.tools.profiling import TOOLS as PROFILING_TOOLS
from fm_mcp.tools.risk import TOOLS as RISK_TOOLS
from fm_mcp.tools.workflow import TOOLS as WORKFLOW_TOOLS

ALL_TOOLS = WORKFLOW_TOOLS + APPROVAL_TOOLS + RISK_TOOLS + NOTIFICATION_TOOLS + COLLECTOR_TOOLS + PROFILING_TOOLS


def register_tools(mcp: FastMCP) -> None:
    """Attach every supported FM MCP tool to a FastMCP server."""
    for tool in ALL_TOOLS:
        mcp.tool()(tool)
