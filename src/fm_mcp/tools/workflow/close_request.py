"""Close an FM request."""

from typing import Any
from uuid import UUID

from fm_mcp.tools import _client


def close_request(request_id: str) -> dict[str, Any]:
    """Đóng request đã được phê duyệt."""
    result = _client._call("POST", f"/api/v1/requests/{UUID(request_id)}/close")
    assert isinstance(result, dict)
    return result
