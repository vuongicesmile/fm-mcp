"""Get risk heatmap data."""

from typing import Any

from fm_mcp.tools import _client


def get_risk_heatmap() -> list[dict[str, Any]]:
    """Lấy số lượng rủi ro theo ma trận likelihood/impact."""
    result = _client._call("GET", "/api/v1/risks/heatmap")
    assert isinstance(result, list)
    return result
