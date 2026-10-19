"""List workflow definitions."""

from typing import Any

from fm_mcp.tools import _client


def list_workflows() -> list[dict[str, Any]]:
    """Lấy workflow definitions đang hoạt động."""
    result = _client._call("GET", "/api/v1/workflows")
    assert isinstance(result, list)
    return result
