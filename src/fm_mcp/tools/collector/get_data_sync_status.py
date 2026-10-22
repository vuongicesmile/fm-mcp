"""Read a data collector status."""

from typing import Any

from fm_mcp.clients.collector_api import call
from fm_mcp.tools.collector._shared import connection_path


def get_data_sync_status(connection_id: str) -> dict[str, Any]:
    """Xem trạng thái worker và lượt đồng bộ mới nhất của một nguồn dữ liệu."""
    result = call("GET", f"{connection_path(connection_id)}/capture/status")
    assert isinstance(result, dict)
    return result
