"""Development lab guards and SQL-backed layer assessment contracts."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from fm_mcp.profiling import service


@pytest.mark.asyncio
async def test_bad_data_lab_never_mutates_outside_development(monkeypatch):
    monkeypatch.setattr(service, "settings", replace(service.settings, environment="production"))
    monkeypatch.setattr(service, "_seed_bad_layers", lambda: pytest.fail("Warehouse mutation must not run"))
    with pytest.raises(ValueError, match="development"):
        await service.seed_bad_data_demo()


@pytest.mark.asyncio
async def test_layer_runs_use_actual_query_results_instead_of_fixed_scores(monkeypatch):
    manifest = {"rows": 15, "valid_rows": 9, "quarantined_rows": 5, "deduplicated_rows": 1,
                "statuses": [{"quality_status": "NegativeEnergy", "rows": 5}], "reconciled": True}
    monkeypatch.setattr(service, "_seed_bad_layers", lambda: manifest)
    calls = []

    def profile(connection_id, table, capture_id, *, demo_layer=None):
        calls.append(demo_layer)
        return {"connection_id": connection_id, "table": table, "capture_id": capture_id,
                "rows": 9 if demo_layer == "marts" else 15, "quality_score": 73,
                "status": "warn", "violations": [], "dimensions": {"validity": {"score": 100}}}

    async def save(**kwargs):
        return {"result": kwargs["result"]}

    monkeypatch.setattr(service, "_profile_sync", profile)
    monkeypatch.setattr(service.repository, "create", AsyncMock(side_effect=save))
    runs = await service.seed_bad_data_demo()
    assert calls == [None, "staging", "marts"]
    assert [run["result"]["quality_score"] for run in runs] == [73, 67, 73]
    assert runs[1]["result"]["violations"][0]["count"] == 5
    assert runs[2]["result"]["status"] == "warn"
    assert service.repository.create.await_count == 3
