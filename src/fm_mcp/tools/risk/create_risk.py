"""Create a risk."""

from typing import Any
from uuid import UUID

from fm_mcp.tools import _client


def create_risk(
    title: str,
    description: str,
    owner_id: str,
    request_id: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Tạo rủi ro trong Risk Register qua REST API."""
    payload: dict[str, Any] = {
        "title": title,
        "description": description,
        "owner_id": owner_id,
        "category": category,
    }
    if request_id:
        payload["request_id"] = str(UUID(request_id))
    result = _client._call("POST", "/api/v1/risks", payload)
    assert isinstance(result, dict)
    return result
