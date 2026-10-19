"""List FM notifications."""

from typing import Any

from fm_mcp.tools import _client


def get_notifications() -> dict[str, Any]:
    """Lấy notification records mà người dùng được phép xem."""
    result = _client._call("GET", "/api/v1/notifications")
    assert isinstance(result, dict)
    return result
