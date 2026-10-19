"""Create an FM request."""

from typing import Any

from fm_mcp.tools import _client


def create_request(
    workflow_definition_id: str,
    request_type: str,
    title: str,
    description: str | None = None,
    priority: str = "medium",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tạo FM request mới; context chứa dẫn chứng đã được Control Plane xác thực."""
    result = _client._call("POST", "/api/v1/requests", {
        "workflow_definition_id": workflow_definition_id,
        "request_type": request_type,
        "title": title,
        "description": description,
        "priority": priority,
        "context": context or {},
    })
    assert isinstance(result, dict)
    return result
