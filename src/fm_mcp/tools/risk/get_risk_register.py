"""Query the risk register."""

from typing import Any

from fm_mcp.tools import _client


def get_risk_register(status: str | None = None) -> dict[str, Any]:
    """Truy vấn Risk Register, có thể lọc theo status."""
    suffix = f"?status={status}" if status else ""
    result = _client._call("GET", f"/api/v1/risks{suffix}")
    assert isinstance(result, dict)
    return result
