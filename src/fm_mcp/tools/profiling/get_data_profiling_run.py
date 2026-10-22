"""Read one FM-owned data profiling run."""

from typing import Any

from fm_mcp.profiling.service import get_run


async def get_data_profiling_run(run_id: str) -> dict[str, Any]:
    """Return one persisted data-profiling result by its opaque run identifier."""
    return await get_run(run_id)
