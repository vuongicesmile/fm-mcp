"""Cấu hình kết nối REST API Workflow Automation cho MCP adapter."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    # Các fallback hỗ trợ scaffold cũ trong khi deployment chuyển sang tên mới.
    workflow_api_url: str = os.getenv(
        "FM_WORKFLOW_API_URL",
        os.getenv("FM_CONTROL_PLANE_URL", os.getenv("FM_API_URL", "http://localhost:8000")),
    )
    fm_api_timeout: float = float(os.getenv("FM_API_TIMEOUT", "30"))
    environment: str = os.getenv("FM_ENV", "development")
    workflow_api_audience: str = os.getenv("FM_WORKFLOW_API_AUDIENCE", "fm-workflow-api")
    mcp_dev_user_id: str | None = os.getenv("FM_MCP_DEV_USER_ID")
    mcp_dev_roles: str = os.getenv("FM_MCP_DEV_ROLES", "fm_admin")
    mcp_transport: str = os.getenv("FM_MCP_TRANSPORT", "stdio")
    mcp_host: str = os.getenv("FM_MCP_HOST", "127.0.0.1")
    mcp_port: int = int(os.getenv("FM_MCP_PORT", "8000"))
    mcp_path: str = os.getenv("FM_MCP_PATH", "/mcp")


settings = Settings()
