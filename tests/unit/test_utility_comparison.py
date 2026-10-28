from datetime import date

import pytest

from fm_mcp.profiling import utility_comparison as comparison


def reading(building="source:BLD120", name="Retail Hà Nội 120", meter="source:EM120-1", **overrides):
    return {"building_id": building, "building_name": name, "meter_id": meter,
            "equipment_id": None, "object_id": meter + "|energy", "source_system": "file_spo",
            "connection_id": "source", "object_type": "Energy", "meter_level": "Main",
            "first_date": "2026-08-01", "last_date": "2026-10-02", "available_days": 60,
            "previous_sum": 100, "current_sum": 120, "previous_days": 2, "current_days": 2,
            "previous_complete_days": 2, "current_complete_days": 2, **overrides}


@pytest.fixture
def warehouse(monkeypatch):
    state = {"series": [reading()], "queries": []}
    monkeypatch.setattr(comparison, "periods", lambda: (date(2026, 9, 1), date(2026, 10, 1), 2))
    monkeypatch.setattr(comparison, "_database_name", lambda layer: "tenant_one_" + layer)

    class Client:
        def query_json(self, sql, *, parameters=None):
            state["queries"].append((sql, parameters))
            assert "demo_" not in sql
            assert "`tenant_one_marts`" in sql
            assert "readonly=2" in sql
            if ".rpt_building" in sql:
                return [{"building_id": "source:BLD120", "name": "Retail Hà Nội 120"},
                        {"building_id": "other:BLD120", "name": "Retail Hà Nội 120"},
                        {"building_id": "source:NO-HISTORY", "name": "Chưa đo"}]
            if "UNION DISTINCT" in sql:
                return [{"id": "source:EM120-1", "building_id": "source:BLD120", "name": "Công tơ 120", "data_origin": "SYNTHETIC_VN_REALISTIC"}]
            if "toDayOfMonth" in sql:
                return [{"day": 1, "previous_value": 50, "current_value": 60},
                        {"day": 2, "previous_value": 50, "current_value": 60}]
            return state["series"]

    monkeypatch.setattr(comparison, "ClickHouseClient", Client)
    return state


def test_reads_marts_catalog_and_complete_consumption(warehouse):
    result = comparison.energy_comparison()
    assert result["demo"] is False
    assert result["dataset"] == "`tenant_one_marts`.agg_meter_daily"
    assert len(result["options"]["building"]) == 3
    assert "source:NO-HISTORY" in result["options"]["building"]
    assert result["option_labels"]["building"]["source:BLD120"] == "Retail Hà Nội 120 · source:BLD120"
    assert result["complete"] and result["change_pct"] == 20
    assert len(result["daily"]) == 2
    assert result["data_origins"] == ["SYNTHETIC_VN_REALISTIC"]


@pytest.mark.parametrize("filter_value", ["retail ha noi 120", "Hà Nội", "source:BLD120"])
def test_name_filters_are_accent_insensitive_and_ids_exact(warehouse, filter_value):
    assert len(comparison.energy_comparison(building=filter_value)["rows"]) == 1
    assert not comparison.energy_comparison(building="source:BLD12")["rows"]


def test_no_history_is_not_zero_or_demo(warehouse):
    warehouse["series"] = [reading(previous_days=0, current_days=0, previous_complete_days=0, current_complete_days=0,
                                   previous_sum=None, current_sum=None)]
    result = comparison.energy_comparison()
    assert result["previous_value"] is None and result["current_value"] is None
    assert result["change_pct"] is None and not result["daily"] and not result["groups"]
    assert "2026-08-01" in result["message"]


def test_missing_hours_or_quality_failure_blocks_comparison(warehouse):
    warehouse["series"] = [reading(current_complete_days=1)]
    result = comparison.energy_comparison()
    assert result["current_value"] == 120
    assert result["change_pct"] is None and not result["complete"] and not result["daily"]
    sql = next(sql for sql, _ in warehouse["queries"] if "previous_complete_days" in sql)
    for check in ("missing_hours=0", "reset_count=0", "gap_count=0", "spike_count=0", "critical_count=0"):
        assert check in sql
    assert result["coverage"]["reason"] == "incomplete_quality"
    assert result["coverage"]["periods"]["current"]["rejected_meter_days"] == 1
    assert result["coverage"]["periods"]["current"]["missing_meter_days"] == 0


def test_missing_period_has_actionable_diagnostics_not_fake_zero(warehouse):
    warehouse["series"] = [reading(previous_days=0, previous_complete_days=0, previous_sum=0)]
    result = comparison.energy_comparison()
    assert result["coverage"]["reason"] == "missing_history"
    assert result["coverage"]["periods"]["previous"] == {
        "start": "2026-09-01", "expected_meter_days": 2, "valid_meter_days": 0,
        "complete_meter_days": 0, "missing_meter_days": 2, "rejected_meter_days": 0,
    }
    assert result["previous_value"] is None and result["change_pct"] is None
    assert "Tháng 09/2026" in result["message"]
    assert "đồng bộ lịch sử" in result["message"]


def test_first_day_of_month_is_distinct_from_missing_history(warehouse, monkeypatch):
    monkeypatch.setattr(comparison, "periods", lambda: (date(2026, 9, 1), date(2026, 10, 1), 0))
    warehouse["series"] = [reading(previous_days=0, current_days=0, previous_complete_days=0, current_complete_days=0)]
    result = comparison.energy_comparison()
    assert result["coverage"]["reason"] == "no_completed_days"
    assert not result["complete"] and result["change_pct"] is None


def test_default_does_not_double_count_main_and_hvac(warehouse):
    warehouse["series"].append(reading(meter="source:EM120-2", meter_level="HVAC", current_sum=80))
    result = comparison.energy_comparison()
    assert result["current_value"] == 120
    assert "source:EM120-2" in result["options"]["equipment"]
    selected = comparison.energy_comparison(equipment="source:EM120-2")
    assert selected["current_value"] == 80


def test_identical_building_names_stay_source_scoped(warehouse):
    warehouse["series"].append(reading(building="other:BLD120", meter="other:EM120-1"))
    result = comparison.energy_comparison(building="Retail Hà Nội 120")
    assert len(result["groups"]) == 2
    assert len(comparison.energy_comparison(building="source:BLD120")["groups"]) == 1


def test_water_uses_canonical_volume_and_legacy_object_alias(warehouse):
    warehouse["series"] = [reading(object_type="WaterConsumption", meter_level=None)]
    result = comparison.energy_comparison(metric="water", object_type="Consumption")
    assert result["unit"] == "m³" and result["complete"]
    assert "previous_kwh" not in result and "previous_kwh" not in result["rows"][0]
    _sql, params = next((sql, params) for sql, params in warehouse["queries"] if "previous_complete_days" in sql)
    assert params["unit"] == "m3" and params["metric"] == "water"
    assert not comparison.energy_comparison(metric="water", object_type="Energy")["rows"]


def test_zero_previous_period_has_no_infinite_percentage(warehouse):
    warehouse["series"] = [reading(previous_sum=0)]
    result = comparison.energy_comparison()
    assert result["complete"] and result["previous_value"] == 0 and result["change_pct"] is None


@pytest.mark.parametrize("args", [{"metric": "water; DROP TABLE"}, {"group_by": "sql"}, {"object_type": "Voltage"}, {"building": "x" * 201}])
def test_rejects_unsupported_filters_before_database_access(monkeypatch, args):
    monkeypatch.setattr(comparison, "ClickHouseClient", lambda: pytest.fail("Warehouse must not be accessed"))
    with pytest.raises(ValueError):
        comparison.energy_comparison(**args)


def test_tool_uses_real_marts_service():
    from fm_mcp.tools.profiling.get_energy_comparison import energy_comparison
    assert energy_comparison is comparison.energy_comparison
