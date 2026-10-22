"""Seed explicitly labelled local demo findings through an MCP tool."""

from typing import Any

from fm_mcp.profiling.service import seed_demo


async def seed_data_profiling_demo() -> list[dict[str, Any]]:
    """Create labelled RMIT FM demo findings without mutating any raw source."""
    return await seed_demo()
