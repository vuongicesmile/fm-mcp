"""Return a bounded, PII-masked sample without exposing source credentials."""

from typing import Any

from fm_mcp.profiling.service import get_masked_sample


async def get_masked_raw_sample(
    connection_id: str, table: str, sample: int = 20,
) -> dict[str, Any]:
    """Return up to fifty masked rows for a selected raw FM table."""
    return await get_masked_sample(connection_id, table, sample)
