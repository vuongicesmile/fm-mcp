"""Pipeline tools validate identifiers before calling the tenant-scoped API."""

import pytest

from fm_mcp.tools.collector.get_data_sync_events import get_data_sync_events
from fm_mcp.tools.collector.get_data_sync_run import get_data_sync_run


@pytest.mark.parametrize("identifier", ["../secret", "invalid", "a" * 33, "A" * 32])
def test_pipeline_tools_reject_invalid_identifiers(identifier):
    with pytest.raises(ValueError):
        get_data_sync_run(identifier)
    with pytest.raises(ValueError):
        get_data_sync_events(identifier)


def test_pipeline_events_reject_negative_cursor():
    with pytest.raises(ValueError):
        get_data_sync_events("a" * 32, -1)
