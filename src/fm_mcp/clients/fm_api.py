"""HTTP client for the Workflow Automation REST API."""

import httpx

from fm_mcp.core.config import settings


def create_client() -> httpx.Client:
    """Create a configured client for the MCP adapter."""
    return httpx.Client(base_url=settings.workflow_api_url, timeout=settings.fm_api_timeout)
