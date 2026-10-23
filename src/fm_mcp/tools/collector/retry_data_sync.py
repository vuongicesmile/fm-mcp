"""Retry a previously captured collector batch."""

from typing import Any

from fm_mcp.clients.collector_api import call
from fm_mcp.tools.collector._shared import connection_path


def retry_data_sync(connection_id: str = "", run_id: str | None = None) -> dict[str, Any]:
    """Nạp lại batch đã thu bị lỗi, không mở một phiên capture mới."""
    if run_id is not None:
        if connection_id:
            raise ValueError("Specify either connection_id or run_id, not both")
        from fm_mcp.tools.collector._shared import pipeline_path
        result = call("POST", pipeline_path(run_id) + "/retry")
    else:
        result = call("POST", f"{connection_path(connection_id)}/sync/retry")
    assert isinstance(result, dict)
    return result
