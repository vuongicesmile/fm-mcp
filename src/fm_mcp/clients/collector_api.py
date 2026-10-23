"""Client for the tenant-scoped collector contract owned by Titan Control Plane."""

from typing import Any

import httpx

from fm_mcp.core.config import settings


def _org_id() -> str:
    if not settings.collector_org_id:
        raise RuntimeError("FM_COLLECTOR_ORG_ID is not configured")
    return settings.collector_org_id


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if not settings.collector_service_token:
        raise RuntimeError("FM_COLLECTOR_SERVICE_TOKEN is not configured")
    headers["Authorization"] = f"Bearer {settings.collector_service_token}"
    return headers


def call(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    """Call the configured Control Plane without exposing its credentials to an MCP client."""
    with httpx.Client(base_url=settings.collector_service_url, timeout=settings.fm_api_timeout, trust_env=False) as client:
        response = client.request(method, f"/internal/tenants/{_org_id()}{path}", json=payload, headers=_headers())
        if response.status_code >= 400:
            # Marker an toàn để gateway giữ HTTP conflict/not-found, không echo response chứa config.
            raise RuntimeError(f"Collector operation rejected [{response.status_code}]")
        return response.json()
