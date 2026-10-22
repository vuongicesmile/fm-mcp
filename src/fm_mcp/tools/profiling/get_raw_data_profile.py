"""Read a retained raw-data profiling result."""

from typing import Any
import re

from fm_mcp.clients.collector_api import call


def get_raw_data_profile(run_id: str) -> dict[str, Any]:
    """Đọc kết quả đánh giá raw data đã lưu, gồm score và các cảnh báo kỹ thuật."""
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("run_id must be a 32-character lowercase identifier")
    result = call("GET", f"/data-profiling/runs/{run_id}")
    assert isinstance(result, dict)
    return result
