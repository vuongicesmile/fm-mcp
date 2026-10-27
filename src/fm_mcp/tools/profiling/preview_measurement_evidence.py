"""Expose read-only threshold evidence from cleaned Marts."""

import asyncio

from fm_mcp.profiling.measurement_evidence import EvidenceFilter, MeasurementEvidence


async def preview_measurement_evidence(org_id: str, filters: dict, timezone: str = "Asia/Ho_Chi_Minh") -> dict:
    """Preview up to 20 Valid Marts measurement rows matching a building/equipment/day/unit/threshold filter. Returns provenance and immutable row identifiers for workflow attachments; no Raw or quarantined readings. Does not create or submit a request."""
    parsed = EvidenceFilter.model_validate(filters)
    return await asyncio.to_thread(lambda: MeasurementEvidence(org_id, parsed.connection_id, timezone).preview(parsed))
