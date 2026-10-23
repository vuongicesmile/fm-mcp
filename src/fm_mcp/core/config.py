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
    collector_org_id: str | None = os.getenv("FM_COLLECTOR_ORG_ID")
    collector_service_url: str = os.getenv("FM_COLLECTOR_SERVICE_URL", "http://collector:8021")
    collector_service_token: str | None = os.getenv("FM_COLLECTOR_SERVICE_TOKEN")
    # Data profiling is owned by FM MCP.  The Control Plane only dispatches MCP
    # calls and must not receive warehouse credentials or profiling SQL.
    profiling_clickhouse_url: str = os.getenv(
        "FM_PROFILING_CLICKHOUSE_URL", "http://host.docker.internal:8123"
    )
    profiling_clickhouse_user: str = os.getenv("FM_PROFILING_CLICKHOUSE_USER", "titan")
    profiling_clickhouse_password: str = os.getenv("FM_PROFILING_CLICKHOUSE_PASSWORD", "titan-dev")
    profiling_raw_schema: str = os.getenv("FM_PROFILING_RAW_SCHEMA", "t_rmit_fm_raw")
    profiling_org_id: str = os.getenv(
        "FM_PROFILING_ORG_ID", os.getenv("FM_COLLECTOR_ORG_ID", "rmit_fm")
    )


settings = Settings()
