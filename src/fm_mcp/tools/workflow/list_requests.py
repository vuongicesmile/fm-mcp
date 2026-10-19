"""List FM requests."""

from typing import Any

from fm_mcp.tools import _client


def list_requests() -> dict[str, Any]:
    """Lấy các request của danh tính MCP hiện tại, gồm draft và request đã gửi."""
    result = _client._call("GET", "/api/v1/requests")
    assert isinstance(result, dict)
    return result
