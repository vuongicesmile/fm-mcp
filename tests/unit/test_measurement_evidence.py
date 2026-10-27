from dataclasses import replace
from datetime import date

import pytest

from fm_mcp.profiling import measurement_evidence as evidence


@pytest.fixture
def warehouse(monkeypatch):
    state = {"queries": []}
    monkeypatch.setattr(evidence, "settings", replace(evidence.settings, profiling_org_id="tenant_one"))
    monkeypatch.setattr(evidence, "_database_name", lambda layer: "tenant_one_" + layer)

    class Client:
        def query_json(self, sql, *, parameters):
            state["queries"].append((sql, parameters))
            assert "_raw" not in sql and "__canonical" not in sql
            assert "`tenant_one_marts`" in sql and "readonly=2" in sql
            assert parameters["connection"] == "bms_main"
            if "observed_count" in sql:
                return [{"observed_count": 2, "matched_count": 1, "capture_count": 1,
                         "first_observed_at": "2026-10-27 01:00:00", "last_observed_at": "2026-10-27 02:00:00",
                         "min_matched_value": 32, "max_matched_value": 32}]
            if "maxOrNull(source_timestamp) AS latest" in sql:
                return [{"latest": "2026-10-27 02:00:00", "capture_count": 1}]
            if "SELECT building_id AS building_code" in sql:
                return [{"building_code": "bms_main:B1", "name": "Tòa nhà 1"}]
            if "SELECT DISTINCT building_code" in sql:
                return [{"building_code": "bms_main:B1", "equipment_code": "bms_main:E1", "name": "AHU", "equipment_type": "AHU", "object_type": "Temperature", "unit": "C"}]
            return [{"id": "bms_main:P1|t1", "record_id": "bms_main:P1|t1", "source_timestamp": "2026-10-27 02:00:00.123", "captured_at": None,
                     "quality_status": "Valid", "value": 32, "capture_id": "batch-1"}]

    monkeypatch.setattr(evidence, "ClickHouseClient", Client)
    return state


def filters(**changes):
    return evidence.EvidenceFilter(connection_id="bms_main", building_code="bms_main:B1", object_type="Temperature", unit="C",
                                   day=date(2026, 10, 27), threshold=30, **changes)


def test_catalog_and_preview_only_query_cleaned_marts(warehouse):
    reader = evidence.MeasurementEvidence("tenant_one", "bms_main")
    catalog = reader.catalog()
    assert catalog["layer"] == "marts" and catalog["latest_day"] == "2026-10-27"
    snapshot = reader.preview(filters())
    assert snapshot["schema_version"] == 2
    assert snapshot["source"]["dataset"] == "tenant_one_marts.int_reading"
    assert snapshot["rows"][0]["id"] == "bms_main:P1|t1"
    assert snapshot["rows"][0]["source_timestamp"] == "2026-10-27T02:00:00.123000+00:00"
    for sql, _ in warehouse["queries"]:
        if "int_reading" in sql:
            assert "quality_status='Valid'" in sql and "is_valid_for_aggregation=1" in sql
            assert "r.connection_id={connection:String}" in sql


def test_filters_are_bound_and_day_uses_tenant_timezone(warehouse):
    evidence.MeasurementEvidence("tenant_one", "bms_main", "Asia/Ho_Chi_Minh").preview(filters())
    sql, parameters = warehouse["queries"][-1]
    assert "value > {threshold:Float64}" in sql
    assert parameters["start"] == "2026-10-26T17:00:00+00:00"
    assert parameters["end"] == "2026-10-27T17:00:00+00:00"
    assert parameters["building"] == "bms_main:B1" and parameters["threshold"] == "30.0"


def test_rejects_cross_tenant_before_database_access(monkeypatch):
    monkeypatch.setattr(evidence, "settings", replace(evidence.settings, profiling_org_id="tenant_one"))
    monkeypatch.setattr(evidence, "ClickHouseClient", lambda: pytest.fail("Must reject before querying"))
    with pytest.raises(ValueError, match="tenant"):
        evidence.MeasurementEvidence("tenant_two", "bms_main")


@pytest.mark.parametrize("changes", [{"operator": "gt; DROP TABLE"}, {"threshold": float("nan")}, {"table": "raw"}])
def test_rejects_arbitrary_query_or_non_finite_filter(changes):
    data = filters().model_dump()
    with pytest.raises(ValueError):
        evidence.EvidenceFilter.model_validate({**data, **changes})


def test_rejects_duplicate_evidence_row_ids(warehouse, monkeypatch):
    reader = evidence.MeasurementEvidence("tenant_one", "bms_main")
    query = reader.query
    monkeypatch.setattr(reader, "query", lambda sql, parameters: ([{"id": "same"}, {"id": "same"}]
                       if "ORDER BY value" in sql else query(sql, parameters)))
    with pytest.raises(ValueError, match="not unique"):
        reader.preview(filters())
