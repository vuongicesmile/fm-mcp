"""Cancel a collector synchronization job."""

from typing import Any

from fm_mcp.clients.collector_api import call
from fm_mcp.tools.collector._shared import connection_path


def cancel_data_sync(connection_id: str = "", run_id: str | None = None) -> dict[str, Any]:
    """Yêu cầu hủy lượt đồng bộ đang hoạt động của một nguồn dữ liệu."""
    if run_id is not None:
        if connection_id:
            raise ValueError("Specify either connection_id or run_id, not both")
        from fm_mcp.tools.collector._shared import pipeline_path
        result = call("POST", pipeline_path(run_id) + "/cancel")
    else:
        result = call("POST", f"{connection_path(connection_id)}/capture/cancel")
    assert isinstance(result, dict)
    return result
