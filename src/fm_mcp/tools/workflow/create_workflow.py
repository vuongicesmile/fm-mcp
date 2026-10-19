"""Create workflow definitions."""

from typing import Any

from fm_mcp.tools import _client


def create_workflow(
    code: str,
    name: str,
    description: str | None = None,
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Tạo và publish workflow definition; steps phải chứa approver_ids trong conditions."""
    result = _client._call("POST", "/api/v1/workflows", {
        "code": code,
        "name": name,
        "description": description,
        "steps": steps or [],
    })
    assert isinstance(result, dict)
    return result
