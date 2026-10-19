"""Submit an FM request."""

from typing import Any
from uuid import UUID

from fm_mcp.tools import _client


def submit_request(request_id: str) -> dict[str, Any]:
    """Gửi request vào approval workflow."""
    result = _client._call("POST", f"/api/v1/requests/{UUID(request_id)}/submit")
    assert isinstance(result, dict)
    return result
