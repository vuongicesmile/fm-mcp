"""Create an opt-in Raw -> Staging -> Marts data-quality demonstration."""

from typing import Any

from fm_mcp.profiling.service import seed_bad_data_demo


async def seed_bad_data_profiling_demo() -> list[dict[str, Any]]:
    """Create deterministic bad Raw rows and derived layer results in development only."""
    return await seed_bad_data_demo()
