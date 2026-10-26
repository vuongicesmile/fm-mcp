"""Read the BMS overview from tenant-configured reporting marts."""

import asyncio
import unicodedata
from urllib.parse import urlencode

from fm_mcp.profiling.clickhouse import ClickHouseClient
from fm_mcp.profiling.service import LIMITS, _database_name


def _dashboard(filters: dict[str, str]) -> dict:
    client = ClickHouseClient()
    schema = _database_name("marts")
    source = f"""SELECT c.object_id AS point_id, coalesce(p.name,c.object_id) AS point_name, c.building_id AS building_id,
        b.name AS building_name, coalesce(c.equipment_id,p.equipment_id,c.meter_id) AS equipment_id,
        coalesce(e.name,e.equipment_id,c.meter_id) AS equipment_name,
        coalesce(e.equipment_type,if(em.meter_id IS NOT NULL,'ElectricityMeter',if(wm.meter_id IS NOT NULL,'WaterMeter',NULL))) AS equipment_type,
        coalesce(e.status,em.status,wm.status,'Unknown') AS status,
        c.object_type AS object_type, c.unit AS unit, c.current_value AS current_value, c.last_reading_time_local AS measured_at
        FROM `{schema}`.int_point_current c
        LEFT JOIN `{schema}`.rpt_point p ON p.point_id=c.object_id
        LEFT JOIN `{schema}`.rpt_building b ON c.building_id=b.building_id
        LEFT JOIN `{schema}`.rpt_equipment e ON coalesce(c.equipment_id,p.equipment_id)=e.equipment_id
        LEFT JOIN `{schema}`.dim_electric_meter em ON c.meter_id=em.meter_id
        LEFT JOIN `{schema}`.dim_water_meter wm ON c.meter_id=wm.meter_id
        WHERE c.quality_status_last='Valid'"""
    inventory = f"""SELECT b.building_id AS building_id,b.name AS building_name,
        e.equipment_id AS equipment_id,coalesce(e.name,e.equipment_id) AS equipment_name,
        e.equipment_type AS equipment_type,coalesce(e.status,'Unknown') AS status
        FROM `{schema}`.rpt_building b LEFT JOIN `{schema}`.rpt_equipment e ON b.building_id=e.building_id"""
    allowed = {"building": ("building_id", "building_name"), "equipment": ("equipment_id", "equipment_name"),
               "equipment_type": ("equipment_type",), "status": ("status",),
               "object_type": ("object_type",), "unit": ("unit",)}
    clauses = []
    inventory_clauses = []
    parameters = {}
    for key, value in filters.items():
        if len(value) > 200:
            raise ValueError("Dashboard filter is too long")
        if value:
            parameters[key] = value
            if key in {"building", "equipment"} and ":" not in value:
                parameters[key] = "".join(c for c in unicodedata.normalize("NFD", value.casefold().replace("đ", "d")) if unicodedata.category(c) != "Mn")
                expressions = []
                for column in allowed[key]:
                    text = f"replaceAll(replaceRegexpAll(normalizeUTF8NFD(lowerUTF8(ifNull({column}, ''))), '\\\\p{{M}}', ''), 'đ', 'd')"
                    expressions.append(f"positionUTF8({text}, {{{key}:String}})>0")
                clauses.append("(" + " OR ".join(expressions) + ")")
            else:
                clauses.append("(" + " OR ".join(f"lowerUTF8(ifNull({column}, ''))=lowerUTF8({{{key}:String}})" for column in allowed[key]) + ")")
            if key not in {"object_type", "unit"}:
                inventory_clauses.append(clauses[-1])
    base = f"WITH source AS ({source}) SELECT * FROM source" + (" WHERE " + " AND ".join(clauses) if clauses else "")
    asset_base = f"SELECT * FROM ({inventory})" + (" WHERE " + " AND ".join(inventory_clauses) if inventory_clauses else "")
    def query(sql: str):
        return client.query_json(sql + " " + LIMITS + ", join_use_nulls = 1", parameters=parameters)
    summary = query(f"SELECT uniqExact(building_id) AS buildings, uniqExact(equipment_id) AS equipment, uniqExactIf(equipment_id, lowerUTF8(status)='active') AS active, uniqExactIf(equipment_id, lowerUTF8(status)='inactive') AS inactive, uniqExactIf(equipment_id, status='Unknown') AS unknown FROM ({asset_base})")[0]
    summary['points'] = query(f"SELECT count() AS points FROM ({base})")[0]['points']
    charts = {}
    for key, column in (("equipment_by_building", "building_name"), ("equipment_by_type", "equipment_type"), ("equipment_by_status", "status"), ("points_by_building", "building_name"), ("points_by_type", "object_type"), ("top_equipment", "equipment_name")):
        metric = "uniqExact(equipment_id)" if key.startswith("equipment_") else "count()"
        charts[key] = query(f"SELECT coalesce({column}, 'Chưa xác định') AS label, {metric} AS value FROM ({asset_base if key.startswith('equipment_') else base}) GROUP BY label ORDER BY value DESC, label LIMIT {5 if key == 'top_equipment' else 30}")
    options = {}
    for key, column in (("building", "building_name"), ("equipment", "equipment_name"), ("equipment_type", "equipment_type"), ("status", "status"), ("object_type", "object_type"), ("unit", "unit")):
        option_source = inventory if key in {"building", "equipment", "equipment_type", "status"} else source
        options[key] = [row["value"] for row in query(f"SELECT DISTINCT {column} AS value FROM ({option_source}) WHERE {column} IS NOT NULL ORDER BY value LIMIT 1000")]
    building_options = query(f"SELECT building_id,name FROM `{schema}`.rpt_building ORDER BY building_id LIMIT 1000")
    options['building'] = [r['building_id'] for r in building_options]
    options['equipment'] = sorted(set(options['equipment']) | {r['value'] for r in query(f"SELECT DISTINCT equipment_id AS value FROM ({source}) WHERE equipment_id IS NOT NULL LIMIT 1000")})
    return {"dashboard_type": "bms_overview", "filters": filters, "summary": summary, "charts": charts, "options": options,
            "option_labels": {"building": {r['building_id']: f"{r['name']} · {r['building_id']}" for r in building_options}},
            "equipment_rows": query(f"SELECT i.building_name,i.equipment_name,i.equipment_type,i.status,coalesce(q.points,0) AS points FROM ({asset_base}) i LEFT JOIN (SELECT equipment_id,count() AS points FROM ({base}) GROUP BY equipment_id) q ON i.equipment_id=q.equipment_id ORDER BY i.building_id,i.equipment_id LIMIT 100"),
            "rows": query(f"{base} ORDER BY building_id, equipment_id, point_id LIMIT 100"),
            "source": f"{schema}: rpt_building, rpt_equipment, int_point_current, rpt_point, dim_electric_meter, dim_water_meter", "quality_scope": "Valid",
            "dashboard_url": "/dashboards/bms-overview?" + urlencode({k: v for k, v in filters.items() if v}),
            "message": f"Dashboard có {summary['buildings']} bản ghi tòa nhà trong danh mục, {summary['equipment']} thiết bị và {summary['points']} điểm đo hợp lệ. Bộ lọc đã được áp dụng."}


async def get_bms_dashboard(building: str = "", equipment: str = "", equipment_type: str = "", status: str = "", object_type: str = "", unit: str = "") -> dict:
    """Open or filter the BMS overview dashboard using cleaned Marts. Reuse existing conversation filters when changing a building or measuring device. Empty strings clear filters. Returns a dashboard_url for the Portal."""
    return await asyncio.to_thread(_dashboard, {"building": building, "equipment": equipment, "equipment_type": equipment_type, "status": status, "object_type": object_type, "unit": unit})
