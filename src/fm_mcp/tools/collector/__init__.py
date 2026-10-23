"""Data collector MCP tools."""

from fm_mcp.tools.collector.cancel_data_sync import cancel_data_sync
from fm_mcp.tools.collector.check_data_source import test_data_source
from fm_mcp.tools.collector.get_data_sync_events import get_data_sync_events
from fm_mcp.tools.collector.get_data_sync_run import get_data_sync_run
from fm_mcp.tools.collector.get_data_sync_status import get_data_sync_status
from fm_mcp.tools.collector.list_data_sync_jobs import list_data_sync_jobs
from fm_mcp.tools.collector.list_data_sync_runs import list_data_sync_runs
from fm_mcp.tools.collector.retry_data_sync import retry_data_sync
from fm_mcp.tools.collector.sync_data import sync_data

TOOLS = (
    test_data_source,
    get_data_sync_status,
    list_data_sync_jobs,
    sync_data,
    cancel_data_sync,
    retry_data_sync,
    get_data_sync_run,
    get_data_sync_events,
    list_data_sync_runs,
)
