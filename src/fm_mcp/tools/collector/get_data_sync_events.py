"""Đọc nhật ký sự kiện đã lọc secret của pipeline collector."""

import re
from typing import Any

from fm_mcp.clients.collector_api import call


def get_data_sync_events(run_id: str, after_id: int = 0) -> dict[str, Any]:
    """Đọc tối đa 100 sự kiện từ cursor; không trả config, token hoặc dữ liệu nguồn."""
    if not re.fullmatch(r"[0-9a-f]{32}", run_id) or after_id < 0:
        raise ValueError("Invalid pipeline event cursor")
    result = call("GET", f"/pipelines/{run_id}/events?after={after_id}")
    assert isinstance(result, dict)
    return result
