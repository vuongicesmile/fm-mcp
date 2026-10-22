"""Create a bounded, read-only raw-data profile."""

from typing import Any

from fm_mcp.clients.collector_api import call
from fm_mcp.tools.collector._shared import connection_path


def profile_raw_data(connection_id: str, table: str, capture_id: str | None = None) -> dict[str, Any]:
    """Đánh giá completeness và duplicate của một bảng raw; không sửa Bronze hay ClickHouse."""
    connection_path(connection_id)
    if not table or len(table) > 120:
        raise ValueError("table must be a valid raw table name")
    payload: dict[str, Any] = {"connection_id": connection_id, "table": table}
    if capture_id is not None:
        payload["capture_id"] = capture_id
    result = call("POST", "/data-profiling/runs", payload)
    assert isinstance(result, dict)
    return result
