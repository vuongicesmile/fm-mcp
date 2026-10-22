"""Test a data collector source."""

from typing import Any

from fm_mcp.clients.collector_api import call
from fm_mcp.tools.collector._shared import connection_path


def test_data_source(connection_id: str) -> dict[str, Any]:
    """Kiểm tra kết nối BMS hoặc SPO trước khi đồng bộ; không tạo batch dữ liệu."""
    result = call("POST", f"{connection_path(connection_id)}/test")
    assert isinstance(result, dict)
    return result
