"""MCP tools that proxy supported Workflow Automation REST endpoints."""

from typing import Any
from uuid import UUID

from fastmcp import FastMCP

from fm_mcp.clients.fm_api import create_client
from fm_mcp.core.config import settings


def _call(
    method: str, path: str, payload: dict[str, Any] | None = None, extra_headers: dict[str, str] | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    headers: dict[str, str] = {}
    if settings.mcp_dev_user_id:
        headers["X-Authenticated-User-Id"] = settings.mcp_dev_user_id
        headers["X-Authenticated-Roles"] = settings.mcp_dev_roles
    headers.update(extra_headers or {})
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
    def create_workflow(
        code: str,
        name: str,
        description: str | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Tạo và publish workflow definition; steps phải chứa approver_ids trong conditions."""
        result = _call("POST", "/api/v1/workflows", {
            "code": code,
            "name": name,
            "description": description,
            "steps": steps or [],
        })
        assert isinstance(result, dict)
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
    def list_requests() -> dict[str, Any]:
        """Lấy các request của danh tính MCP hiện tại, gồm draft và request đã gửi."""
        result = _call("GET", "/api/v1/requests")
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

    @mcp.tool()
    def get_pending_approvals() -> dict[str, Any]:
        """Lấy các approval step hiện tại người dùng được phép xử lý."""
        result = _call("GET", "/api/v1/approvals/pending")
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def approve_request(approval_step_id: str, comment: str | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
        """Phê duyệt một approval step; danh tính được chuyển tiếp từ MCP runtime."""
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        result = _call("POST", f"/api/v1/approvals/{UUID(approval_step_id)}/approve", {"comment": comment}, headers)
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def reject_request(approval_step_id: str, comment: str | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
        """Từ chối một approval step."""
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        result = _call("POST", f"/api/v1/approvals/{UUID(approval_step_id)}/reject", {"comment": comment}, headers)
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def get_approval_history(approval_step_id: str) -> list[dict[str, Any]]:
        """Lấy lịch sử action của một approval step."""
        result = _call("GET", f"/api/v1/approvals/{UUID(approval_step_id)}/history")
        assert isinstance(result, list)
        return result

    @mcp.tool()
    def create_risk(title: str, description: str, owner_id: str, request_id: str | None = None, category: str | None = None) -> dict[str, Any]:
        """Tạo rủi ro trong Risk Register qua REST API."""
        payload = {"title": title, "description": description, "owner_id": owner_id, "category": category}
        if request_id:
            payload["request_id"] = str(UUID(request_id))
        result = _call("POST", "/api/v1/risks", payload)
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def update_risk(risk_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Cập nhật chủ sở hữu, mitigation plan hoặc trạng thái rủi ro."""
        result = _call("PATCH", f"/api/v1/risks/{UUID(risk_id)}", changes)
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def get_risk_register(status: str | None = None) -> dict[str, Any]:
        """Truy vấn Risk Register, có thể lọc theo status."""
        suffix = f"?status={status}" if status else ""
        result = _call("GET", f"/api/v1/risks{suffix}")
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def assess_risk(risk_id: str, likelihood: int, impact: int, assessment_type: str, notes: str | None = None) -> dict[str, Any]:
        """Ghi nhận assessment rủi ro; score mặc định là likelihood × impact."""
        result = _call("POST", f"/api/v1/risks/{UUID(risk_id)}/assessments", {
            "likelihood": likelihood, "impact": impact, "assessment_type": assessment_type, "notes": notes,
        })
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def get_risk_heatmap() -> list[dict[str, Any]]:
        """Lấy số lượng rủi ro theo ma trận likelihood/impact."""
        result = _call("GET", "/api/v1/risks/heatmap")
        assert isinstance(result, list)
        return result

    @mcp.tool()
    def get_notifications() -> dict[str, Any]:
        """Lấy notification records mà người dùng được phép xem."""
        result = _call("GET", "/api/v1/notifications")
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def send_notification(
        recipient_id: str, recipient_address: str, event_code: str, body: str,
        subject: str | None = None, request_id: str | None = None,
    ) -> dict[str, Any]:
        """Queue email; the trusted SMTP dispatcher delivers it asynchronously."""
        payload: dict[str, Any] = {"recipient_id": recipient_id, "recipient_address": recipient_address,
                                   "channel": "email", "event_code": event_code, "payload": {"body": body}}
        if request_id:
            payload["request_id"] = str(UUID(request_id))
        # A configured template has precedence. Subject is retained in payload for a fallback template.
        if subject:
            payload["payload"]["subject"] = subject
        result = _call("POST", "/api/v1/notifications", payload)
        assert isinstance(result, dict)
        return result

    @mcp.tool()
    def get_overdue_requests() -> dict[str, Any]:
        """Lấy request quá hạn; backend yêu cầu role fm_admin."""
        result = _call("GET", "/api/v1/requests/overdue")
        assert isinstance(result, dict)
        return result
