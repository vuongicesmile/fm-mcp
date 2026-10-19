"""Update an FM request."""

from typing import Any
from uuid import UUID

from fm_mcp.tools import _client


def update_request(request_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Cập nhật request draft hoặc returned."""
    result = _client._call("PATCH", f"/api/v1/requests/{UUID(request_id)}", changes)
    assert isinstance(result, dict)
    return result
