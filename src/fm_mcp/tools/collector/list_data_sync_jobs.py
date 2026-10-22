"""List collector jobs."""

from typing import Any

from fm_mcp.clients.collector_api import call
from fm_mcp.tools.collector._shared import connection_path


def list_data_sync_jobs(connection_id: str, limit: int = 20) -> dict[str, Any]:
    """Liệt kê lịch sử đồng bộ gần nhất của một nguồn, gồm trạng thái và lỗi đã được lọc an toàn."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    result = call("GET", f"{connection_path(connection_id)}/capture/jobs?limit={limit}")
    assert isinstance(result, dict)
    return result
