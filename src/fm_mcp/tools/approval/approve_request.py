"""Approve an FM request."""

from typing import Any
from uuid import UUID

from fm_mcp.tools import _client


def approve_request(
    approval_step_id: str,
    comment: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Phê duyệt một approval step; danh tính được chuyển tiếp từ MCP runtime."""
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    result = _client._call(
        "POST",
        f"/api/v1/approvals/{UUID(approval_step_id)}/approve",
        {"comment": comment},
        headers,
    )
    assert isinstance(result, dict)
    return result
