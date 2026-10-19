"""List pending approvals."""

from typing import Any

from fm_mcp.tools import _client


def get_pending_approvals() -> dict[str, Any]:
    """Lấy các approval step hiện tại người dùng được phép xử lý."""
    result = _client._call("GET", "/api/v1/approvals/pending")
    assert isinstance(result, dict)
    return result
