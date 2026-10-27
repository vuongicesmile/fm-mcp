"""Read immutable workflow evidence exclusively from cleaned tenant marts."""

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from fm_mcp.core.config import settings
from fm_mcp.profiling.clickhouse import ClickHouseClient
from fm_mcp.profiling.service import _database_name

OPERATORS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
LIMITS = "SETTINGS max_execution_time=15, max_result_rows=10001, result_overflow_mode='throw', readonly=2, join_use_nulls=1"
COVERAGE_NOTE = "Dẫn chứng lấy từ Marts, chỉ gồm số đo Valid đã qua xử lý. Không dùng Raw hoặc bản ghi cách ly; không có mẫu khớp không chứng minh thiết bị hoạt động bình thường. Số mẫu không phải số sự cố hoặc thời lượng vượt ngưỡng."


class EvidenceFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    connection_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    building_code: str = Field(min_length=1, max_length=256)
    equipment_type: str = Field(default="", max_length=256)
    equipment_code: str = Field(default="", max_length=256)
    object_type: str = Field(min_length=1, max_length=256)
    unit: str = Field(min_length=1, max_length=64)
    day: date
    operator: Literal["gt", "gte", "lt", "lte"] = "gt"
    threshold: float


def _instant(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(UTC).isoformat()


class MeasurementEvidence:
    def __init__(self, org_id: str, connection_id: str, timezone: str = "Asia/Ho_Chi_Minh"):
        if org_id != settings.profiling_org_id:
            raise ValueError("Evidence tenant does not match the configured warehouse")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", connection_id):
            raise ValueError("Invalid evidence connection identifier")
        self.zone = ZoneInfo(timezone)
        self.timezone, self.connection_id = timezone, connection_id
        self.schema = _database_name("marts")
        self.client = ClickHouseClient()

    def query(self, sql, parameters=None):
        return self.client.query_json(sql + " " + LIMITS, parameters={"connection": self.connection_id, **(parameters or {})})

    def observations(self):
        schema = self.schema
        # Dimension và giá trị đều ở Marts; ID có tiền tố nguồn không được ghép theo tên.
        return f"""SELECT r.reading_key AS id,r.reading_key AS record_id,r.batch_id AS capture_id,
            r.object_id AS object_id,coalesce(p.name,r.object_id) AS object_name,
            r.object_type AS object_type,r.canonical_unit AS unit,r.building_id AS building_code,
            coalesce(b.name,r.building_id) AS building_name,
            coalesce(r.equipment_id,r.meter_id,r.object_id) AS equipment_code,
            coalesce(e.name,r.equipment_id,r.meter_id,r.object_id) AS equipment_name,
            coalesce(e.equipment_type,if(em.meter_id IS NOT NULL,'ElectricityMeter',if(wm.meter_id IS NOT NULL,'WaterMeter','Unknown'))) AS equipment_type,
            toFloat64(r.value) AS value,r.reading_time_utc AS source_timestamp,
            r.ingested_at_utc AS captured_at,r.source_record_id AS source_record_id,
            r.quality_status AS quality_status,r.rule_version AS rule_version,
            r.data_origin AS data_origin,'marts_reading' AS observation_kind
            FROM `{schema}`.int_reading r
            LEFT JOIN `{schema}`.rpt_building b ON r.building_id=b.building_id
            LEFT JOIN `{schema}`.rpt_equipment e ON r.equipment_id=e.equipment_id
            LEFT JOIN `{schema}`.rpt_point p ON r.object_id=p.point_id
            LEFT JOIN `{schema}`.dim_electric_meter em ON r.meter_id=em.meter_id
            LEFT JOIN `{schema}`.dim_water_meter wm ON r.meter_id=wm.meter_id
            WHERE r.connection_id={{connection:String}} AND r.quality_status='Valid'
            AND r.is_valid_for_aggregation=1 AND r.value IS NOT NULL AND isFinite(toFloat64(r.value))
            AND notEmpty(ifNull(r.reading_key,'')) AND r.canonical_unit IS NOT NULL"""

    def catalog(self):
        source = self.observations()
        buildings = self.query(f"""SELECT building_id AS building_code,name FROM `{self.schema}`.rpt_building
            WHERE startsWith(building_id,concat({{connection:String}},':')) ORDER BY building_code LIMIT 1001""")
        equipment = self.query(f"""SELECT DISTINCT building_code,equipment_code,equipment_name AS name,equipment_type
            FROM ({source}) ORDER BY building_code,equipment_code LIMIT 5001""")
        measurements = self.query(f"""SELECT DISTINCT building_code,equipment_code,object_type,unit
            FROM ({source}) ORDER BY building_code,equipment_code,object_type,unit LIMIT 10001""")
        if len(buildings) > 1000 or len(equipment) > 5000 or len(measurements) > 10000:
            raise ValueError("Evidence catalog exceeds supported limits; narrow the configured source")
        times = self.query(f"SELECT maxOrNull(source_timestamp) AS latest,uniqExact(capture_id) AS capture_count FROM ({source})")[0]
        latest = _instant(times.get("latest"))
        return {"buildings": buildings, "equipment": equipment, "measurements": measurements,
                "timezone": self.timezone, "latest_day": datetime.fromisoformat(latest).astimezone(self.zone).date().isoformat() if latest else None,
                "capture_count": int(times["capture_count"]), "coverage_note": COVERAGE_NOTE,
                "layer": "marts", "dataset": f"{self.schema}.int_reading", "quality_scope": "Valid"}

    def preview(self, filters: EvidenceFilter):
        if filters.connection_id != self.connection_id:
            raise ValueError("Evidence source mismatch")
        # Khoảng ngày theo tenant, chuyển sang UTC trước khi lọc; không ép mọi ngày dài 24 giờ.
        start = datetime.combine(filters.day, time.min, self.zone).astimezone(UTC)
        end = datetime.combine(filters.day + timedelta(days=1), time.min, self.zone).astimezone(UTC)
        parameters = {"building": filters.building_code, "equipment": filters.equipment_code,
                      "equipment_type": filters.equipment_type, "object_type": filters.object_type, "unit": filters.unit,
                      "start": start.isoformat(), "end": end.isoformat(), "threshold": str(filters.threshold)}
        base = f"""SELECT * FROM ({self.observations()})
            WHERE building_code={{building:String}} AND object_type={{object_type:String}} AND unit={{unit:String}}
            AND ({{equipment:String}}='' OR equipment_code={{equipment:String}})
            AND ({{equipment_type:String}}='' OR equipment_type={{equipment_type:String}})
            AND source_timestamp>=parseDateTime64BestEffort({{start:String}},3,'UTC')
            AND source_timestamp<parseDateTime64BestEffort({{end:String}},3,'UTC')"""
        condition = f"value {OPERATORS[filters.operator]} {{threshold:Float64}}"
        summary = self.query(f"""SELECT count() AS observed_count,countIf({condition}) AS matched_count,
            minOrNull(source_timestamp) AS first_observed_at,maxOrNull(source_timestamp) AS last_observed_at,
            minIfOrNull(value,{condition}) AS min_matched_value,maxIfOrNull(value,{condition}) AS max_matched_value,
            uniqExact(capture_id) AS capture_count FROM ({base})""", parameters)[0]
        direction = "DESC" if filters.operator in {"gt", "gte"} else "ASC"
        rows = self.query(f"SELECT * FROM ({base}) WHERE {condition} ORDER BY value {direction},source_timestamp,id LIMIT 20", parameters)
        if len({row["id"] for row in rows}) != len(rows):
            raise ValueError("Marts evidence identifiers are not unique")
        for row in rows:
            for key in ("source_timestamp", "captured_at"):
                row[key] = _instant(row.get(key))
        for key in ("first_observed_at", "last_observed_at"):
            summary[key] = _instant(summary.get(key))
        capture_count = int(summary.pop("capture_count"))
        return {"kind": "fm_measurement_evidence", "schema_version": 2,
                "source": {"id": self.connection_id, "name": self.connection_id, "layer": "marts",
                           "dataset": f"{self.schema}.int_reading", "quality_scope": "Valid"},
                "filters": filters.model_dump(mode="json"), "timezone": self.timezone, "summary": summary,
                "rows": rows, "sample_limit": 20, "coverage_note": COVERAGE_NOTE,
                "capture_count": capture_count, "generated_at": datetime.now(UTC).isoformat()}
