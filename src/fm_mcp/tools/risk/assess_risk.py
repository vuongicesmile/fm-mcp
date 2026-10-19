"""Assess an FM risk."""

from typing import Any
from uuid import UUID

from fm_mcp.tools import _client


def assess_risk(
    risk_id: str,
    likelihood: int,
    impact: int,
    assessment_type: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Ghi nhận assessment rủi ro; score mặc định là likelihood × impact."""
    result = _client._call("POST", f"/api/v1/risks/{UUID(risk_id)}/assessments", {
        "likelihood": likelihood,
        "impact": impact,
        "assessment_type": assessment_type,
        "notes": notes,
    })
    assert isinstance(result, dict)
    return result
