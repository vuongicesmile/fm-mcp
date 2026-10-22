"""List FM raw assets available for profiling."""

from typing import Any

from fm_mcp.clients.collector_api import call


def list_raw_data_assets() -> list[dict[str, Any]]:
    """Liệt kê các bảng raw BMS/SPO mà tenant hiện có thể đánh giá chất lượng."""
    result = call("GET", "/data-profiling/assets")
    assert isinstance(result, list)
    return result
