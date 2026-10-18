"""MCP tools that proxy supported Workflow Automation REST endpoints."""

from typing import Any
from uuid import UUID

from fastmcp import FastMCP

from fm_mcp.clients.fm_api import create_client
from fm_mcp.core.config import settings


def _call(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    headers: dict[str, str] = {}
    if settings.mcp_dev_user_id:
        headers["X-Authenticated-User-Id"] = settings.mcp_dev_user_id
        headers["X-Authenticated-Roles"] = settings.mcp_dev_roles
    with create_client() as client:
        response = client.request(method, path, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_workflows() -> list[dict[str, Any]]:
        """Lấy workflow definitions đang hoạt động."""
        result = _call("GET", "/api/v1/workflows")
        assert isinstance(result, list)
        return result

    @mcp.tool()
    def create_request(
        workflow_definition_id: str,
        request_type: str,
        title: str,
        description: str | None = None,
        priority: str = "medium",
    ) -> dict[str, Any]:
        """Tạo FM request mới qua Workflow Automation API."""
        result = _call("POST", "/api/v1/requests", {
            "workflow_definition_id": workflow_definition_id,
            "request_type": request_type,
            "title": title,
            "description": description,
            "priority": priority,
        })
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def get_request(request_id: str) -> dict[str, Any]:
        """Lấy chi tiết một FM request."""
        result = _call("GET", f"/api/v1/requests/{UUID(request_id)}")
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def update_request(request_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Cập nhật request draft hoặc returned."""
        result = _call("PATCH", f"/api/v1/requests/{UUID(request_id)}", changes)
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def submit_request(request_id: str) -> dict[str, Any]:
        """Gửi request vào approval workflow."""
        result = _call("POST", f"/api/v1/requests/{UUID(request_id)}/submit")
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def close_request(request_id: str) -> dict[str, Any]:
        """Đóng request đã được phê duyệt."""
        result = _call("POST", f"/api/v1/requests/{UUID(request_id)}/close")
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def get_request_history(request_id: str) -> list[dict[str, Any]]:
        """Lấy lịch sử trạng thái request."""
        result = _call("GET", f"/api/v1/requests/{UUID(request_id)}/history")
        assert isinstance(result, list)
        return result
