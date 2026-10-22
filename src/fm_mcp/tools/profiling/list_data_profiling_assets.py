"""List raw FM assets available to the MCP-owned profiling domain."""

from typing import Any

from fm_mcp.profiling.service import list_assets


async def list_data_profiling_assets() -> list[dict[str, Any]]:
    """List BMS and SPO raw tables that can be assessed by FM MCP."""
    return await list_assets()
