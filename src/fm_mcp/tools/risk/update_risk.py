"""Update a risk."""

from typing import Any
from uuid import UUID

from fm_mcp.tools import _client


def update_risk(risk_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Cập nhật chủ sở hữu, mitigation plan hoặc trạng thái rủi ro."""
    result = _client._call("PATCH", f"/api/v1/risks/{UUID(risk_id)}", changes)
    assert isinstance(result, dict)
    return result
