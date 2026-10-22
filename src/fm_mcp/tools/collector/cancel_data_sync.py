"""Cancel a collector synchronization job."""

from typing import Any

from fm_mcp.clients.collector_api import call
from fm_mcp.tools.collector._shared import connection_path


def cancel_data_sync(connection_id: str) -> dict[str, Any]:
    """Yêu cầu hủy lượt đồng bộ đang hoạt động của một nguồn dữ liệu."""
    result = call("POST", f"{connection_path(connection_id)}/capture/cancel")
    assert isinstance(result, dict)
    return result
