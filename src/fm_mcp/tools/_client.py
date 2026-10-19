"""Shared REST client for FM MCP tools."""

from typing import Any

from fm_mcp.clients.fm_api import create_client
from fm_mcp.core.config import settings


def _call(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Call the Workflow Automation API with the configured MCP identity."""
    headers: dict[str, str] = {}
    if settings.mcp_dev_user_id:
        headers["X-Authenticated-User-Id"] = settings.mcp_dev_user_id
        headers["X-Authenticated-Roles"] = settings.mcp_dev_roles
    headers.update(extra_headers or {})
    with create_client() as client:
        response = client.request(method, path, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
