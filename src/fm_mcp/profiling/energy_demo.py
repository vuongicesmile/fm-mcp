"""Deterministic cumulative-register demo for comparable monthly energy periods."""

from calendar import monthrange
from datetime import datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fm_mcp.core.config import settings
from fm_mcp.profiling.clickhouse import ClickHouseClient
from fm_mcp.profiling.service import _database_name, _schema


def periods():
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    current = today.replace(day=1)
    previous = (current - timedelta(days=1)).replace(day=1)
    days = min(today.day - 1, monthrange(previous.year, previous.month)[1])
    return previous, current, days


def seed_energy_demo():
    """Ghi lại riêng bảng demo; giữ nguyên các nguồn và số liệu nghiệp vụ hiện có."""
    if settings.environment != "development":
        raise ValueError("Energy demo is available only in development")
    client = ClickHouseClient()
    raw, staging, marts = _schema(), _database_name("staging"), _database_name("marts")
    previous, current, days = periods()
    end = current + timedelta(days=days)
    values = []
    for building, rate in (("Building A", 100), ("Building B", 200)):
        counter = 10000
        day = previous
        while day <= end:
            values.append(f"('{building}','{day}',{counter})")
            counter += rate if day < current else rate * 1.2
            day += timedelta(days=1)
    client.execute(f"CREATE TABLE IF NOT EXISTS {raw}.demo_energy_registers (building String,reading_date Date,energy_kwh Decimal(18,3)) ENGINE=MergeTree ORDER BY (building,reading_date)")
    client.execute(f"ALTER TABLE {raw}.demo_energy_registers ADD COLUMN IF NOT EXISTS meter String DEFAULT concat('demo:MAIN-',right(building,1))")
    client.execute(f"TRUNCATE TABLE {raw}.demo_energy_registers")
    client.execute(f"INSERT INTO {raw}.demo_energy_registers (building,reading_date,energy_kwh) VALUES " + ",".join(values))
    client.execute(f"""CREATE OR REPLACE VIEW `{staging}`.demo_energy_delta AS
        SELECT building,meter, reading_date - 1 AS day,energy_kwh-previous_value AS consumption_kwh
        FROM (SELECT *,lagInFrame(energy_kwh) OVER (PARTITION BY building ORDER BY reading_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS previous_value,
        row_number() OVER (PARTITION BY building ORDER BY reading_date) AS sequence FROM {raw}.demo_energy_registers)
        WHERE sequence>1 AND energy_kwh>=previous_value""")
    client.execute(f"CREATE OR REPLACE VIEW `{marts}`.demo_energy_daily AS SELECT building,meter,day,consumption_kwh FROM `{staging}`.demo_energy_delta")
    # Bộ nước độc lập đơn vị; không cộng chung m³ với kWh.
    water = [f"('{b}','demo:WATER-{b[-1]}','{day}',{value})" for b, rate in (("Building A", 10), ("Building B", 20))
             for day, value in _registers(previous, current, end, rate)]
    client.execute(f"CREATE TABLE IF NOT EXISTS {raw}.demo_water_registers (building String,meter String,reading_date Date,volume_m3 Decimal(18,3)) ENGINE=MergeTree ORDER BY (building,meter,reading_date)")
    client.execute(f"TRUNCATE TABLE {raw}.demo_water_registers")
    client.execute(f"INSERT INTO {raw}.demo_water_registers VALUES " + ",".join(water))
    client.execute(f"""CREATE OR REPLACE VIEW `{staging}`.demo_water_delta AS
        SELECT building,meter,reading_date-1 AS day,volume_m3-previous_value AS consumption
        FROM (SELECT *,lagInFrame(volume_m3) OVER (PARTITION BY building,meter ORDER BY reading_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS previous_value,
        row_number() OVER (PARTITION BY building,meter ORDER BY reading_date) AS sequence FROM {raw}.demo_water_registers)
        WHERE sequence>1 AND volume_m3>=previous_value""")
    client.execute(f"CREATE OR REPLACE VIEW `{marts}`.demo_water_daily AS SELECT building,meter,day,consumption FROM `{staging}`.demo_water_delta")
    return {"rows": len(values), "previous_month": str(previous), "current_month": str(current), "comparable_days": days}


def _registers(previous, current, end, rate):
    counter = 1000
    day = previous
    while day <= end:
        yield day, counter
        counter += rate if day < current else rate * 0.9
        day += timedelta(days=1)


def energy_comparison(building: str = "", equipment: str = "", metric: str = "electricity", object_type: str = "", group_by: str = "building"):
    """So sánh MTD cùng số ngày; không cộng trực tiếp chỉ số công tơ lũy kế."""
    if settings.environment != "development":
        raise ValueError("Energy demo is available only in development")
    previous, current, days = periods()
    if metric not in {"electricity", "water"} or group_by not in {"building", "equipment", "object_type"}:
        raise ValueError("Unsupported comparison metric or grouping")
    if object_type not in {"", "Energy", "Consumption"}:
        raise ValueError("Unsupported comparison object type")
    if len(building) > 200 or len(equipment) > 200:
        raise ValueError("Energy comparison filter is too long")
    table = f"`{_database_name('marts')}`.demo_{'energy' if metric == 'electricity' else 'water'}_daily"
    measure = "consumption_kwh" if metric == "electricity" else "consumption"
    kind, unit = ("Energy", "kWh") if metric == "electricity" else ("Consumption", "m³")
    client = ClickHouseClient()
    rows = client.query_json(f"""SELECT building,meter,
        toFloat64(sumIf({measure},day>={{previous:Date}} AND day<addDays({{previous:Date}},{{days:UInt32}}))) AS previous_kwh,
        toFloat64(sumIf({measure},day>={{current:Date}} AND day<addDays({{current:Date}},{{days:UInt32}}))) AS current_kwh,
        countIf(day>={{previous:Date}} AND day<addDays({{previous:Date}},{{days:UInt32}})) AS previous_days,
        countIf(day>={{current:Date}} AND day<addDays({{current:Date}},{{days:UInt32}})) AS current_days
        FROM {table}
        WHERE positionCaseInsensitiveUTF8(building,{{building:String}})>0
        AND positionCaseInsensitiveUTF8(meter,{{equipment:String}})>0
        GROUP BY building,meter ORDER BY building,meter""",
        parameters={"previous": str(previous), "current": str(current), "days": str(days), "building": building, "equipment": equipment})
    choices = client.query_json(f"SELECT DISTINCT building,meter FROM {table} ORDER BY building,meter LIMIT 100")
    if object_type and object_type != kind:
        rows = []
    for row in rows:
        row.update(previous_value=row['previous_kwh'], current_value=row['current_kwh'], object_type=kind)
        row['change_pct'] = round(100 * (row['current_value'] - row['previous_value']) / row['previous_value'], 2) if row['previous_value'] and days > 0 and row['previous_days'] == row['current_days'] == days else None
    daily = client.query_json(f"""SELECT toDayOfMonth(day) AS day_number,
        toFloat64(sumIf({measure},day>={{previous:Date}} AND day<addDays({{previous:Date}},{{days:UInt32}}))) AS previous_value,
        toFloat64(sumIf({measure},day>={{current:Date}} AND day<addDays({{current:Date}},{{days:UInt32}}))) AS current_value
        FROM {table} WHERE positionCaseInsensitiveUTF8(building,{{building:String}})>0 AND positionCaseInsensitiveUTF8(meter,{{equipment:String}})>0
        AND ((day>={{previous:Date}} AND day<addDays({{previous:Date}},{{days:UInt32}})) OR (day>={{current:Date}} AND day<addDays({{current:Date}},{{days:UInt32}})))
        GROUP BY toDayOfMonth(day) ORDER BY day_number""", parameters={"previous": str(previous), "current": str(current), "days": str(days), "building": building, "equipment": equipment}) if rows else []
    for row in daily:
        row['day'] = row.pop('day_number', row.get('day'))
    groups = {}
    for row in rows:
        label = row['meter'] if group_by == 'equipment' else row[group_by]
        group = groups.setdefault(label, {"label": label, "previous_value": 0, "current_value": 0})
        for key in ('previous_value', 'current_value'):
            group[key] += row[key]
    before = sum(row['previous_kwh'] for row in rows)
    after = sum(row['current_kwh'] for row in rows)
    complete = bool(rows) and days > 0 and all(row['previous_days'] == days and row['current_days'] == days for row in rows)
    # Không vẽ số 0 từ sumIf như một ngày thực sự không tiêu thụ khi thiếu coverage.
    if not complete:
        daily = []
    change = round(100 * (after - before) / before, 2) if before and complete else None
    filters = {"building": building,"equipment": equipment,"metric": metric,"object_type": object_type,"group_by": group_by}
    result = {"demo": True, "dataset": table, "metric": metric,"unit": unit, "previous_value": before,"current_value": after,"groups": list(groups.values()),"daily": daily, "previous_month": str(previous), "current_month": str(current),
            "days": days, "complete": complete, "previous_kwh": before, "current_kwh": after,
            "change_pct": change, "rows": rows, "filters": filters,
            "options": {"building": sorted({row['building'] for row in choices}),"equipment": sorted({row['meter'] for row in choices}),"object_type": [kind]},
            "dashboard_url": "/dashboards/energy-comparison?" + urlencode({key: value for key,value in filters.items() if value}),
            "message": (f"Dữ liệu demo: so sánh {days} ngày hoàn tất đầu tháng {current:%m/%Y} với cùng {days} ngày tháng {previous:%m/%Y}. "
                        f"{'Điện năng' if metric == 'electricity' else 'Nước tiêu thụ'} tháng này {after:,.1f} {unit}, kỳ trước {before:,.1f} {unit}; thay đổi {change:+.2f}%. "
                        "Tính từ chênh lệch chỉ số công tơ; chưa bao gồm ngày đang diễn ra.") if change is not None else ("Không tìm thấy dữ liệu theo bộ lọc hiện tại." if not rows else "Dữ liệu demo chưa đủ ngày để tính phần trăm so sánh.")}
    # Giữ alias kWh cho client điện cũ, không gắn nhầm đơn vị cho dữ liệu nước.
    if metric == 'water':
        for item in [result, *rows]:
            item.pop('previous_kwh', None)
            item.pop('current_kwh', None)
    return result
