"""Expose source-scoped Marts evidence filters."""

import asyncio

from fm_mcp.profiling.measurement_evidence import MeasurementEvidence


async def get_measurement_catalog(org_id: str, connection_id: str, timezone: str = "Asia/Ho_Chi_Minh") -> dict:
    """List building, equipment and measurement filters from cleaned tenant Marts for workflow evidence. Never query Raw. Source-qualified identifiers remain separate."""
    return await asyncio.to_thread(lambda: MeasurementEvidence(org_id, connection_id, timezone).catalog())
