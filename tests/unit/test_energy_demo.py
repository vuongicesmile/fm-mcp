from dataclasses import replace
from datetime import date

import pytest
from fm_mcp.profiling import energy_demo


def test_demo_rejects_production_before_accessing_warehouse(monkeypatch):
    monkeypatch.setattr(energy_demo, "settings", replace(energy_demo.settings, environment="production"))
    for function in (energy_demo.seed_energy_demo, energy_demo.energy_comparison):
        with pytest.raises(ValueError, match="development"):
            function()


@pytest.mark.parametrize("actual_days,expected", [(25, 20), (24, None)])
def test_comparison_requires_equal_complete_periods(monkeypatch, actual_days, expected):
    monkeypatch.setattr(energy_demo, "settings", replace(energy_demo.settings, environment="development"))
    monkeypatch.setattr(energy_demo, "periods", lambda: (date(2026, 9, 1), date(2026, 10, 1), 25))

    class Client:
        def query_json(self, *_args, **_kwargs):
            return [{"building": "Building A", "meter": "demo:MAIN-A", "previous_kwh": 2500, "current_kwh": 3000, "previous_days": 25, "current_days": actual_days}]

    monkeypatch.setattr(energy_demo, "ClickHouseClient", Client)
    result = energy_demo.energy_comparison()
    assert result['change_pct'] == expected
    assert result['complete'] == (actual_days == 25)
    if actual_days != 25:
        assert result['daily'] == []


@pytest.mark.parametrize('metric,unit', [('electricity', 'kWh'), ('water', 'm³')])
def test_grouping_units_and_empty_filters(monkeypatch, metric, unit):
    monkeypatch.setattr(energy_demo, 'settings', replace(energy_demo.settings, environment='development'))
    monkeypatch.setattr(energy_demo, 'periods', lambda: (date(2026, 9, 1), date(2026, 10, 1), 25))

    class Client:
        def query_json(self, sql, **_kwargs):
            assert ('demo_water_daily' in sql) == (metric == 'water')
            if 'toDayOfMonth' in sql:
                return [{'day': 1, 'previous_value': 100, 'current_value': 120}]
            return [{'building': 'Building A', 'meter': 'demo:METER-A', 'previous_kwh': 2500, 'current_kwh': 3000, 'previous_days': 25, 'current_days': 25}]

    monkeypatch.setattr(energy_demo, 'ClickHouseClient', Client)
    result = energy_demo.energy_comparison(metric=metric, group_by='equipment')
    assert result['unit'] == unit
    assert result['groups'][0]['label'] == 'demo:METER-A'
    assert result['daily'][0]['day'] == 1
    assert 'metric=' + metric in result['dashboard_url']
    if metric == 'water':
        assert 'previous_kwh' not in result
        assert 'previous_kwh' not in result['rows'][0]
    else:
        assert result['previous_kwh'] == result['previous_value']
    assert not energy_demo.energy_comparison(metric=metric, object_type='Consumption' if metric == 'electricity' else 'Energy')['rows']


def test_metric_and_group_are_allowlisted(monkeypatch):
    monkeypatch.setattr(energy_demo, 'settings', replace(energy_demo.settings, environment='development'))
    with pytest.raises(ValueError, match='Unsupported'):
        energy_demo.energy_comparison(metric='water; DROP TABLE')
