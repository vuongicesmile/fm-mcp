"""Read FM request status history."""

from typing import Any
from uuid import UUID

from fm_mcp.tools import _client


def get_request_history(request_id: str) -> list[dict[str, Any]]:
    """Lấy lịch sử trạng thái request."""
    result = _client._call("GET", f"/api/v1/requests/{UUID(request_id)}/history")
    assert isinstance(result, list)
    return result
