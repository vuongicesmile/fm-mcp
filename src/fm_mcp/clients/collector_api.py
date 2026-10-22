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
    if settings.collector_api_token:
        headers["Authorization"] = f"Bearer {settings.collector_api_token}"
    return headers


def call(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    """Call the configured Control Plane without exposing its credentials to an MCP client."""
    with httpx.Client(base_url=settings.collector_control_plane_url, timeout=settings.fm_api_timeout) as client:
        response = client.request(method, f"/api/tenants/{_org_id()}{path}", json=payload, headers=_headers())
        response.raise_for_status()
        return response.json()
