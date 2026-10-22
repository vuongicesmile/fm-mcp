"""Retry a previously captured collector batch."""

from typing import Any

from fm_mcp.clients.collector_api import call
from fm_mcp.tools.collector._shared import connection_path


def retry_data_sync(connection_id: str) -> dict[str, Any]:
    """Nạp lại batch đã thu bị lỗi, không mở một phiên capture mới."""
    result = call("POST", f"{connection_path(connection_id)}/sync/retry")
    assert isinstance(result, dict)
    return result
