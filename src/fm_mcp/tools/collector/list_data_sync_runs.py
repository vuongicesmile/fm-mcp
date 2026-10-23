"""Liệt kê pipeline collector đã lọc secret theo tenant của MCP server."""

from urllib.parse import urlencode

from fm_mcp.clients.collector_api import call


def list_data_sync_runs(connection_id: str = "", status: str = "", offset: int = 0, limit: int = 20) -> dict:
    """Xem các lượt thu BMS/SPO, lọc nguồn/trạng thái và phân trang."""
    if not 0 <= offset or not 1 <= limit <= 100:
        raise ValueError("Invalid pipeline pagination")
    query = urlencode({"connection": connection_id, "status": status, "offset": offset, "limit": limit})
    return call("GET", f"/pipelines?{query}")
