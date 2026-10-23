"""Đọc timeline một pipeline theo tenant đã cấu hình của collector."""

import re
from typing import Any

from fm_mcp.clients.collector_api import call


def get_data_sync_run(run_id: str) -> dict[str, Any]:
    """Xem trạng thái, tiến độ, từng bước lỗi và lịch sử attempt của pipeline collector."""
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("Invalid pipeline identifier")
    result = call("GET", f"/pipelines/{run_id}")
    assert isinstance(result, dict)
    return result
