"""Create a finite collector synchronization job."""

from typing import Any

from fm_mcp.clients.collector_api import call
from fm_mcp.tools.collector._shared import connection_path


def sync_data(connection_id: str, request_key: str) -> dict[str, Any]:
    """Tạo một lượt Sync BMS hoặc SPO. Cùng request_key trả về cùng job để tránh thu trùng dữ liệu."""
    if not 8 <= len(request_key) <= 100:
        raise ValueError("request_key must be between 8 and 100 characters")
    result = call("POST", f"{connection_path(connection_id)}/sync", {"request_key": request_key})
    assert isinstance(result, dict)
    return result
