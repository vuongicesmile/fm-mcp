"""Run the FM-owned data profiling workflow for one raw asset."""

from typing import Any

from fm_mcp.profiling.service import run


async def run_data_profiling(
    connection_id: str, table: str, capture_id: str | None = None,
) -> dict[str, Any]:
    """Profile one raw asset and persist its quality result without changing source data."""
    return await run(connection_id, table, capture_id)
