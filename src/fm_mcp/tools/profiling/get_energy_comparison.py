"""Read the clearly labelled development energy comparison fixture."""

import asyncio

from fm_mcp.profiling.energy_demo import energy_comparison


async def get_energy_comparison(building: str = "", equipment: str = "", metric: str = "electricity", object_type: str = "", group_by: str = "building") -> dict:
    """Compare demo electricity (kWh) or water (m³) this month versus the same completed days last month. Filter building/equipment/object_type; group_by building, equipment or object_type. Returns daily series, paired groups, detail, coverage and a dashboard link. Development demo only; no production readings implied."""
    return await asyncio.to_thread(energy_comparison, building, equipment, metric, object_type, group_by)
