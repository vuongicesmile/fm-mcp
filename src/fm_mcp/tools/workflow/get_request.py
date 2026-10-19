"""Get an FM request."""

from typing import Any
from uuid import UUID

from fm_mcp.tools import _client


def get_request(request_id: str) -> dict[str, Any]:
    """Lấy chi tiết một FM request."""
    result = _client._call("GET", f"/api/v1/requests/{UUID(request_id)}")
    assert isinstance(result, dict)
    return result
