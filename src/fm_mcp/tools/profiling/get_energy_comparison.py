"""Read utility consumption comparisons from the configured tenant's marts."""

import asyncio

from fm_mcp.profiling.utility_comparison import energy_comparison


async def get_energy_comparison(building: str = "", equipment: str = "", metric: str = "electricity", object_type: str = "", group_by: str = "building") -> dict:
    """Compare cleaned Marts electricity (kWh) or water (m³) this month versus equal completed days last month. Filter building/equipment by source-qualified ID or partial name; group_by building, equipment or object_type. Returns the full building catalog, meter detail, source provenance, coverage, and dashboard_url. Missing history stays missing, never replaced by demo readings. Default electricity totals exclude classified branch meters to avoid double counting."""
    return await asyncio.to_thread(energy_comparison, building, equipment, metric, object_type, group_by)
