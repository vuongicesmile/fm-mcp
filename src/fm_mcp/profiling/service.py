"""Profiling operations owned by FM MCP, not by Titan Control Plane."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from fm_mcp.core.config import settings
from fm_mcp.profiling import repository
from fm_mcp.profiling.clickhouse import ClickHouseClient, ClickHouseError

IDENT = re.compile(r"^[a-z][a-z0-9_]{1,80}$")
TABLE = re.compile(r"^[a-z][a-z0-9_.]{1,120}$")
CAPTURE = re.compile(r"^[a-f0-9]{32}$")
PII_NAME = re.compile(r"(e_?mail|phone|mobile|contact|address|street|tax_?code|cccd|cmnd|passport|id_card|birth|dob|full_name|first_name|last_name|customer_name|^name$|note|ho_ten|dien_thoai|so_dt|dia_chi|ngay_sinh)", re.IGNORECASE)
NUMERIC = re.compile(r"^(Nullable\()?(U?Int|Float|Decimal)")
MAX_COLUMNS = 80
LIMITS = "SETTINGS max_execution_time = 15, max_result_rows = 1000, readonly = 2"
MASK = "•••"
BAD_CAPTURE_ID = "bad0bad0bad0bad0bad0bad0bad0bad0"
BAD_CONNECTION_ID = "bms_fake"
BAD_TABLE = "profiling_bad_readings"


def _identifier(value: str) -> str:
    if not IDENT.fullmatch(value):
        raise ValueError("Invalid FM profiling identifier")
    return f"`{value}`"


def _schema() -> str:
    return _identifier(settings.profiling_raw_schema)


def _stream(table: str) -> str:
    parent, separator, child = table.partition("__")
    return f"{parent}.{child}" if separator else table


def _catalog(client: ClickHouseClient) -> dict[str, dict[str, Any]]:
    schema = settings.profiling_raw_schema
    tables: dict[str, dict[str, Any]] = {}
    for row in client.query_json(
        "SELECT name, toString(total_rows) AS rows FROM system.tables WHERE database = {database:String}",
        parameters={"database": schema},
    ):
        name = str(row["name"])
        tables[name] = {"rows": int(row["rows"]) if str(row["rows"]).isdigit() else None, "columns": []}
    for row in client.query_json(
        "SELECT table, name, type FROM system.columns WHERE database = {database:String} ORDER BY table, position",
        parameters={"database": schema},
    ):
        table = str(row["table"])
        if table in tables:
            tables[table]["columns"].append({"name": str(row["name"]), "type": str(row["type"])})
    return tables


def _assets() -> list[dict[str, Any]]:
    catalog = _catalog(ClickHouseClient())
    grouped: dict[str, list[dict[str, Any]]] = {}
    for full, meta in sorted(catalog.items()):
        connection_id, separator, table = full.partition("___")
        if not separator or table.startswith(("_dlt", "dlt_")):
            continue
        grouped.setdefault(connection_id, []).append({
            "table": table.replace("__", "."), "stream": _stream(table), "rows": meta["rows"],
            "columns": [column for column in meta["columns"] if not column["name"].startswith("_dlt")],
        })
    return [
        {"connection_id": connection_id, "connector": "spo" if "spo" in connection_id else "bms", "tables": tables}
        for connection_id, tables in grouped.items()
    ]


def _resolve(client: ClickHouseClient, connection_id: str, table: str) -> tuple[str, list[dict[str, Any]]]:
    if not IDENT.fullmatch(connection_id) or not TABLE.fullmatch(table):
        raise ValueError("connection_id or table is invalid")
    full = f"{connection_id}___{table.replace('.', '__')}"
    meta = _catalog(client).get(full)
    if not meta or table.startswith(("_dlt", "dlt_")):
        raise ValueError(f"Raw table '{connection_id}/{table}' was not found")
    return f"{_schema()}.{_identifier(full)}", [c for c in meta["columns"] if not c["name"].startswith("_dlt")][:MAX_COLUMNS]


def _profile_sync(connection_id: str, table: str, capture_id: str | None, *, demo_layer: str | None = None) -> dict[str, Any]:
    client = ClickHouseClient()
    reference, columns = _resolve(client, connection_id, table)
    if demo_layer is not None:
        if settings.environment != "development" or connection_id != BAD_CONNECTION_ID or table != BAD_TABLE or demo_layer not in {"staging", "marts"}:
            raise ValueError("Invalid demo layer")
        suffix = "clean" if demo_layer == "staging" else "valid"
        reference = f"{_identifier(_database_name(demo_layer))}.{_identifier(f'{BAD_TABLE}_{suffix}')}"
    has_capture = "capture_id" in {column["name"] for column in columns}
    if capture_id is not None and not CAPTURE.fullmatch(capture_id):
        raise ValueError("capture_id is invalid")
    if capture_id is not None and not has_capture:
        raise ValueError("This raw table cannot be filtered by capture_id")
    if has_capture and capture_id is None:
        order = "_dlt_load_id" if any(c["name"] == "_dlt_load_id" for c in _catalog(client).get(f"{connection_id}___{table.replace('.', '__')}", {}).get("columns", [])) else "capture_id"
        capture_id = client.scalar(f"SELECT capture_id FROM {reference} WHERE capture_id IS NOT NULL ORDER BY {order} DESC LIMIT 1")
    where, parameters = ("", None)
    if capture_id:
        where, parameters = " WHERE capture_id = {capture_id:String}", {"capture_id": str(capture_id)}

    expressions = ["count() AS rows", "count() - uniqExact(tuple(*)) AS duplicate_rows"]
    for index, column in enumerate(columns):
        name = _identifier(column["name"])
        expressions.extend((
            f"countIf(isNull({name}) OR toString({name}) = '') AS empty_{index}",
            f"uniq({name}) AS distinct_{index}",
        ))
    data = client.query_json(f"SELECT {', '.join(expressions)} FROM {reference}{where} {LIMITS}", parameters=parameters)[0]
    rows = int(data["rows"])
    empty = sum(int(data[f"empty_{index}"]) for index in range(len(columns)))
    cells = rows * len(columns)
    completeness = round(100 * (1 - empty / cells), 1) if cells else None
    profiles = [{
        "name": column["name"], "type": column["type"],
        "empty_rows": int(data[f"empty_{index}"]),
        "empty_pct": round(100 * int(data[f"empty_{index}"]) / rows, 1) if rows else None,
        "distinct_count": int(data[f"distinct_{index}"]),
    } for index, column in enumerate(columns)]
    duplicate_rows = int(data["duplicate_rows"])
    violations: list[dict[str, Any]] = []
    for column in profiles:
        if column["empty_rows"]:
            violations.append({"code": "NULL_BLANK", "severity": "warn", "count": column["empty_rows"], "field": column["name"], "message": f"{column['empty_rows']} giá trị thiếu hoặc trống trong {column['name']}."})
    if not rows:
        violations.append({"code": "EMPTY_TABLE", "severity": "warn", "message": "Không có dòng nào trong phạm vi đã chọn."})
    if duplicate_rows:
        violations.append({"code": "DUPLICATE_ROWS", "severity": "warn", "count": duplicate_rows, "message": "Có dòng trùng hoàn toàn trong raw table."})
    if completeness is not None and completeness < 90:
        violations.append({"code": "LOW_COMPLETENESS", "severity": "warn", "value": completeness, "message": "Tỷ lệ dữ liệu có mặt thấp hơn ngưỡng kỹ thuật 90%."})

    numeric = [(index, column) for index, column in enumerate(columns) if NUMERIC.match(column["type"])][:12]
    if rows >= 8 and numeric:
        quantiles: list[str] = []
        for index, column in numeric:
            value = f"toFloat64OrNull(toString({_identifier(column['name'])}))"
            quantiles.extend((f"quantileExact(0.25)({value}) AS q1_{index}", f"quantileExact(0.75)({value}) AS q3_{index}"))
        quartiles = client.query_json(f"SELECT {', '.join(quantiles)} FROM {reference}{where} {LIMITS}", parameters=parameters)[0]
        for index, column in numeric:
            q1, q3 = quartiles.get(f"q1_{index}"), quartiles.get(f"q3_{index}")
            if q1 is None or q3 is None:
                continue
            lower, upper = float(q1) - 1.5 * (float(q3) - float(q1)), float(q3) + 1.5 * (float(q3) - float(q1))
            value = f"toFloat64OrNull(toString({_identifier(column['name'])}))"
            count = int(client.scalar(f"SELECT countIf({value} < {lower:.12g} OR {value} > {upper:.12g}) FROM {reference}{where} {LIMITS}", parameters=parameters) or 0)
            if count:
                violations.append({"code": "IQR_OUTLIER", "severity": "warn", "count": count, "field": column["name"], "message": f"{count} giá trị vượt ngưỡng IQR; cần đối chiếu ngữ cảnh vận hành."})
    status = "fail" if not rows else "warn" if violations else "pass"
    score = 0 if not rows else max(0, round((completeness or 0) - min(30, 100 * duplicate_rows / rows)))
    dimensions = {
        "completeness": {"score": completeness or 0},
        "uniqueness": {"score": max(0, 100 * (1 - duplicate_rows / rows)) if rows else 0},
        "validity": {"score": 100 if status != "fail" else 0},
        "consistency": {"score": 100 if not violations else max(0, score)},
        "anomaly": {"score": 100 if not any(issue["code"] == "IQR_OUTLIER" for issue in violations) else max(0, score)},
    }
    return {"connection_id": connection_id, "table": table, "capture_id": capture_id, "rows": rows,
            "columns": len(columns), "column_profiles": profiles, "completeness_pct": completeness,
            "duplicate_rows": duplicate_rows, "quality_score": score, "status": status,
            "violations": violations, "dimensions": dimensions, "layer": "bronze"}


def _sample_sync(connection_id: str, table: str, sample: int) -> dict[str, Any]:
    client = ClickHouseClient()
    reference, columns = _resolve(client, connection_id, table)
    sample = max(1, min(sample, 50))
    names = ", ".join(_identifier(column["name"]) for column in columns)
    total_rows = int(client.scalar(f"SELECT count() FROM {reference} {LIMITS}") or 0)
    rows = client.query_json(f"SELECT {names} FROM {reference} LIMIT {sample} {LIMITS}")
    masked_columns = []
    for column in columns:
        pii = bool(PII_NAME.search(column["name"]))
        masked_columns.append({"name": column["name"], "type": column["type"], "pii": pii, "distinct": 0, "empty_pct": None})
        if pii:
            for row in rows:
                if row.get(column["name"]) is not None:
                    row[column["name"]] = MASK
    response = {"connection_id": connection_id, "table": table, "stream": _stream(table.replace(".", "__")), "rows": total_rows, "columns": masked_columns, "sample": rows}
    if connection_id == BAD_CONNECTION_ID and table == BAD_TABLE:
        response["row_annotations"] = _demo_row_annotations(client, rows)
    return response


def _demo_row_annotations(client: ClickHouseClient, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Explain how each intentionally bad demo row is handled by the layer transform."""
    staging = _database_name("staging")
    try:
        quality_rows = client.query_json(
            f"SELECT reading_id, quality_status, quarantine_reason FROM `{staging}`.`{BAD_TABLE}_clean`"
        )
        duplicate_rows = {
            str(item["reading_id"])
            for item in client.query_json(
                f"SELECT reading_id FROM `{_schema().strip('`')}`.`{BAD_CONNECTION_ID}___{BAD_TABLE}` "
                "GROUP BY reading_id HAVING count() > 1"
            )
        }
    except ClickHouseError:
        return []
    by_reading = {str(item["reading_id"]): item for item in quality_rows}
    reasons = {
        "MissingBuilding": "Thiếu mã tòa nhà nên không thể đối chiếu thiết bị với tòa nhà.",
        "MissingEnergy": "Thiếu giá trị điện năng, không đủ dữ liệu để tính chỉ số.",
        "NegativeEnergy": "Điện năng âm, vi phạm quy tắc miền dữ liệu.",
        "DomainOutlier": "Điện năng vượt ngưỡng demo 0–5.000 kWh, cần kiểm tra cảm biến/đơn vị.",
        "Valid": "Đủ điều kiện nghiệp vụ theo các quy tắc demo hiện tại.",
    }
    annotations: list[dict[str, Any]] = []
    for row in rows:
        reading_id = str(row.get("reading_id", ""))
        quality = by_reading.get(reading_id, {})
        status = str(quality.get("quality_status", "Unknown"))
        is_duplicate = reading_id in duplicate_rows
        if status == "Valid" and is_duplicate:
            reason = "Trùng hoàn toàn với một dòng khác trong Raw; vẫn hợp lệ nhưng sẽ được gộp ở Marts."
            action = "Giữ để truy vết ở Silver → gộp dòng trùng khi tạo Marts."
        elif status == "Valid":
            reason = reasons[status]
            action = "Giữ lại ở Silver → nạp vào Marts."
        else:
            reason = reasons.get(status, str(quality.get("quarantine_reason") or "Không đạt quy tắc chất lượng."))
            action = "Gắn quality_status và quarantine_reason ở Silver → không nạp vào Marts."
        annotations.append({
            "quality_status": status,
            "is_valid": status == "Valid",
            "is_duplicate": is_duplicate,
            "reason": reason,
            "transform_action": action,
        })
    return annotations


async def list_assets() -> list[dict[str, Any]]:
    return await asyncio.to_thread(_assets)


async def run(connection_id: str, table: str, capture_id: str | None = None) -> dict[str, Any]:
    result = await asyncio.to_thread(_profile_sync, connection_id, table, capture_id)
    return await repository.create(tenant_id=settings.profiling_org_id, connection_id=connection_id, table=table, capture_id=result.get("capture_id"), result=result)


async def get_run(run_id: str) -> dict[str, Any]:
    return await repository.get(settings.profiling_org_id, run_id)


async def get_overview(
    layer: str = "bronze", year: int | None = None, month: int | None = None,
    include_demo: bool = False,
) -> dict[str, Any]:
    if layer not in {"bronze", "silver", "gold"}:
        raise ValueError("layer must be bronze, silver, or gold")
    if year is not None and not 2000 <= year <= 2200:
        raise ValueError("year is invalid")
    if month is not None and not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    return await repository.overview(
        settings.profiling_org_id, layer=layer, year=year, month=month, include_demo=include_demo
    )


async def get_masked_sample(connection_id: str, table: str, sample: int = 20) -> dict[str, Any]:
    return await asyncio.to_thread(_sample_sync, connection_id, table, sample)


def _demo_result(connection_id: str, table: str, score: int, status: str, rows: int, issues: list[dict[str, Any]], layer: str) -> dict[str, Any]:
    affected = sum(int(issue.get("count", 0)) for issue in issues)
    return {
        "connection_id": connection_id, "table": table, "capture_id": "demo0000000000000000000000000000", "rows": rows, "columns": 12,
        "completeness_pct": round(max(0, 100 - affected / max(rows, 1) * 100), 1), "duplicate_rows": next((int(issue["count"]) for issue in issues if issue["code"] == "DUPLICATE_ROWS"), 0),
        "quality_score": score, "status": status, "violations": issues, "layer": layer, "demo_fixture": True,
        "dimensions": {key: {"score": score if key in {"consistency", "anomaly"} else 100} for key in ("completeness", "uniqueness", "validity", "consistency", "anomaly")},
        "note": "Dữ liệu mô phỏng RMIT FM để trình diễn dashboard; không thay đổi Bronze/raw source.",
    }


async def seed_demo() -> list[dict[str, Any]]:
    if settings.environment != "development":
        raise ValueError("Demo profiling fixtures are available only in development")
    fixtures = [
        ("bms_fake", "buildings", 100, "pass", 12, [], "bronze"),
        ("bms_fake", "equipment", 86, "warn", 31, [{"code": "NULL_BLANK", "severity": "warn", "count": 4, "field": "building_code", "message": "4 thiết bị thiếu mã tòa nhà để đối chiếu quan hệ."}], "bronze"),
        ("bms_fake", "cov_events", 62, "fail", 197, [{"code": "DUPLICATE_ROWS", "severity": "warn", "count": 9, "field": "event_id", "message": "9 sự kiện COV trùng hoàn toàn trong batch mô phỏng."}, {"code": "NEGATIVE_VALUE", "severity": "fail", "count": 3, "field": "value", "message": "3 giá trị đo âm, cần kiểm tra cảm biến hoặc đơn vị đo."}], "bronze"),
        ("rmit_fm_silver", "fact_work_order", 82, "warn", 412, [{"code": "NULL_BLANK", "severity": "warn", "count": 18, "field": "completed_at", "message": "18 work order chưa có thời điểm hoàn tất."}], "silver"),
        ("rmit_fm_gold", "sla_summary", 65, "fail", 18, [{"code": "NEGATIVE_VALUE", "severity": "fail", "count": 2, "field": "sla_compliance_pct", "message": "2 giá trị SLA không hợp lệ, cần kiểm tra phép tính metric."}], "gold"),
    ]
    records = []
    for connection_id, table, score, status, rows, issues, layer in fixtures:
        result = _demo_result(connection_id, table, score, status, rows, issues, layer)
        records.append(await repository.create(tenant_id=settings.profiling_org_id, connection_id=connection_id, table=table, capture_id=result["capture_id"], result=result, is_demo=True))
    return records


def _database_name(suffix: str) -> str:
    raw = settings.profiling_raw_schema
    if not IDENT.fullmatch(raw):
        raise ValueError("FM profiling raw schema is invalid")
    base = raw.removesuffix("_raw")
    value = f"{base}_{suffix}"
    if not IDENT.fullmatch(value):
        raise ValueError("FM profiling layer schema is invalid")
    return value


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _bad_raw_rows() -> list[tuple[Any, ...]]:
    # Các lỗi có chủ đích: trùng toàn dòng, thiếu building/energy, giá trị âm và outlier.
    return [
        (BAD_CAPTURE_ID, "r-001", "B01", "M-001", "2026-10-01 00:00:00.000", 120.0, 24.5, "demo-001"),
        (BAD_CAPTURE_ID, "r-001", "B01", "M-001", "2026-10-01 00:00:00.000", 120.0, 24.5, "demo-001"),
        (BAD_CAPTURE_ID, "r-002", None, "M-001", "2026-10-01 01:00:00.000", 121.0, 24.7, "demo-002"),
        (BAD_CAPTURE_ID, "r-003", "B01", "M-001", "2026-10-01 02:00:00.000", -4.0, 24.6, "demo-003"),
        (BAD_CAPTURE_ID, "r-004", "B01", "M-001", "2026-10-01 03:00:00.000", 9999.0, 24.8, "demo-004"),
        (BAD_CAPTURE_ID, "r-005", "B01", "M-001", "2026-10-01 04:00:00.000", None, 25.0, "demo-005"),
        (BAD_CAPTURE_ID, "r-006", "", "M-002", "2026-10-01 00:00:00.000", 80.0, 23.8, "demo-006"),
        (BAD_CAPTURE_ID, "r-007", "B02", "M-002", "2026-10-01 01:00:00.000", 81.0, 23.9, "demo-007"),
        (BAD_CAPTURE_ID, "r-008", "B02", "M-002", "2026-10-01 02:00:00.000", 82.0, 24.0, "demo-008"),
        (BAD_CAPTURE_ID, "r-009", "B02", "M-002", "2026-10-01 03:00:00.000", 83.0, 24.1, "demo-009"),
    ]


def _seed_bad_layers() -> dict[str, Any]:
    client = ClickHouseClient()
    raw, staging, marts = _schema().strip("`"), _database_name("staging"), _database_name("marts")
    client.execute(f"CREATE DATABASE IF NOT EXISTS `{raw}`")
    client.execute(f"CREATE DATABASE IF NOT EXISTS `{staging}`")
    client.execute(f"CREATE DATABASE IF NOT EXISTS `{marts}`")
    client.execute(f"DROP TABLE IF EXISTS `{raw}`.`{BAD_CONNECTION_ID}___{BAD_TABLE}`")
    client.execute(f"""
        CREATE TABLE `{raw}`.`{BAD_CONNECTION_ID}___{BAD_TABLE}`
        (
            capture_id String, reading_id String, building_code Nullable(String), meter_id String,
            reading_at DateTime64(3, 'UTC'), energy_kwh Nullable(Float64), temperature_c Nullable(Float64),
            source_record_id String
        ) ENGINE = MergeTree ORDER BY (meter_id, reading_at, reading_id)
    """)
    values = ",\n".join("(" + ", ".join(_sql_literal(value) for value in row) + ")" for row in _bad_raw_rows())
    client.execute(f"INSERT INTO `{raw}`.`{BAD_CONNECTION_ID}___{BAD_TABLE}` VALUES {values}")
    client.execute(f"""
        CREATE OR REPLACE VIEW `{staging}`.`{BAD_TABLE}_clean` AS
        SELECT *,
            multiIf(trim(ifNull(building_code, '')) = '', 'MissingBuilding',
                    energy_kwh IS NULL, 'MissingEnergy',
                    energy_kwh < 0, 'NegativeEnergy',
                    energy_kwh > 5000, 'DomainOutlier', 'Valid') AS quality_status,
            quality_status = 'Valid' AS is_valid,
            if(quality_status = 'Valid', NULL, quality_status) AS quarantine_reason
        FROM `{raw}`.`{BAD_CONNECTION_ID}___{BAD_TABLE}`
    """)
    client.execute(f"""
        CREATE OR REPLACE VIEW `{marts}`.`{BAD_TABLE}_valid` AS
        SELECT DISTINCT * FROM `{staging}`.`{BAD_TABLE}_clean` WHERE is_valid
    """)
    client.execute(f"""
        CREATE OR REPLACE VIEW `{marts}`.`{BAD_TABLE}_quality_summary` AS
        SELECT coalesce(building_code, '<missing>') AS building_code,
               quality_status, count() AS rows, countIf(is_valid) AS valid_rows,
               min(energy_kwh) AS min_energy_kwh, max(energy_kwh) AS max_energy_kwh
        FROM `{staging}`.`{BAD_TABLE}_clean`
        GROUP BY building_code, quality_status
        ORDER BY building_code, quality_status
    """)
    total = int(client.scalar(f"SELECT count() FROM `{staging}`.`{BAD_TABLE}_clean`" ) or 0)
    valid = int(client.scalar(f"SELECT count() FROM `{marts}`.`{BAD_TABLE}_valid`" ) or 0)
    quarantined = int(client.scalar(f"SELECT countIf(NOT is_valid) FROM `{staging}`.`{BAD_TABLE}_clean`") or 0)
    duplicates = int(client.scalar(f"SELECT count() - uniqExact(tuple(*)) FROM `{staging}`.`{BAD_TABLE}_clean` WHERE is_valid") or 0)
    statuses = client.query_json(f"SELECT quality_status, count() AS rows FROM `{staging}`.`{BAD_TABLE}_clean` GROUP BY quality_status ORDER BY quality_status")
    return {
        "raw_table": f"{BAD_CONNECTION_ID}/{BAD_TABLE}",
        "staging_view": f"{staging}.{BAD_TABLE}_clean",
        "mart_view": f"{marts}.{BAD_TABLE}_valid",
        "summary_view": f"{marts}.{BAD_TABLE}_quality_summary",
        "rows": total,
        "valid_rows": valid,
        "quarantined_rows": quarantined,
        "deduplicated_rows": duplicates,
        "statuses": statuses,
        "reconciled": total == valid + quarantined + duplicates,
    }


async def seed_bad_data_demo() -> list[dict[str, Any]]:
    """Write a fixed local bad-data set and persist the result for all three layers."""
    if settings.environment != "development":
        raise ValueError("Bad-data demo is available only in development")
    manifest = await asyncio.to_thread(_seed_bad_layers)
    raw_result = await asyncio.to_thread(_profile_sync, BAD_CONNECTION_ID, BAD_TABLE, BAD_CAPTURE_ID)
    raw_result.update({
        "demo_fixture": True, "demo_bad_data": True,
        "note": "Raw demo có lỗi có chủ đích; Staging gắn quality_status/quarantine, Marts chỉ giữ dòng Valid.",
        "demo_manifest": manifest,
    })
    raw_run = await repository.create(
        tenant_id=settings.profiling_org_id, connection_id=BAD_CONNECTION_ID, table=BAD_TABLE,
        capture_id=BAD_CAPTURE_ID, result=raw_result, is_demo=True,
    )
    staging_result = await asyncio.to_thread(_profile_sync, BAD_CONNECTION_ID, BAD_TABLE, BAD_CAPTURE_ID, demo_layer="staging")
    mart_result = await asyncio.to_thread(_profile_sync, BAD_CONNECTION_ID, BAD_TABLE, BAD_CAPTURE_ID, demo_layer="marts")
    codes = {"MissingBuilding": "MISSING_BUILDING", "MissingEnergy": "MISSING_ENERGY", "NegativeEnergy": "NEGATIVE_VALUE", "DomainOutlier": "DOMAIN_OUTLIER"}
    for item in manifest["statuses"]:
        if item["quality_status"] in codes:
            staging_result["violations"].append({"code": codes[item["quality_status"]], "severity": "fail", "count": int(item["rows"]), "message": f"{item['rows']} dòng cách ly: {item['quality_status']}."})
    for result, layer, suffix in ((staging_result, "silver", "clean"), (mart_result, "gold", "valid")):
        result.update({"table": f"{BAD_TABLE}_{suffix}", "layer": layer, "demo_fixture": True, "demo_bad_data": True, "demo_manifest": manifest})
        result["note"] = "Đánh giá SQL trên view demo thực tế; ngưỡng năng lượng 0–5.000 kWh chỉ dùng minh họa."
        invalid = manifest["quarantined_rows"] if layer == "silver" else 0
        result["dimensions"]["validity"] = {"score": round(100 * (1 - invalid / max(result["rows"], 1)), 1)}
        if invalid:
            result["status"] = "fail"
            result["quality_score"] = min(result["quality_score"], round(result["dimensions"]["validity"]["score"]))
    staging_run = await repository.create(
        tenant_id=settings.profiling_org_id, connection_id=BAD_CONNECTION_ID, table=f"{BAD_TABLE}_clean",
        capture_id=BAD_CAPTURE_ID, result=staging_result, is_demo=True,
    )
    mart_run = await repository.create(
        tenant_id=settings.profiling_org_id, connection_id=BAD_CONNECTION_ID, table=f"{BAD_TABLE}_valid",
        capture_id=BAD_CAPTURE_ID, result=mart_result, is_demo=True,
    )
    return [raw_run, staging_run, mart_run]


__all__ = ["ClickHouseError", "get_masked_sample", "get_overview", "get_run", "list_assets", "run", "seed_bad_data_demo", "seed_demo"]
