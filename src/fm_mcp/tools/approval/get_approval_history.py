"""Get approval history for an FM request."""

from typing import Any
from uuid import UUID

from fm_mcp.tools import _client


def get_approval_history(approval_step_id: str) -> list[dict[str, Any]]:
    """Lấy lịch sử action của một approval step."""
    result = _client._call("GET", f"/api/v1/approvals/{UUID(approval_step_id)}/history")
    assert isinstance(result, list)
    return result
