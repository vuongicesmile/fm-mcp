"""Get overdue FM requests."""

from typing import Any

from fm_mcp.tools import _client


def get_overdue_requests() -> dict[str, Any]:
    """Lấy request quá hạn; backend yêu cầu role fm_admin."""
    result = _client._call("GET", "/api/v1/requests/overdue")
    assert isinstance(result, dict)
    return result
