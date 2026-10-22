"""Profiling operations owned by FM MCP, not by Titan Control Plane."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from fm_mcp.core.config import settings
from fm_mcp.profiling.clickhouse import ClickHouseClient, ClickHouseError
from fm_mcp.profiling import repository

IDENT = re.compile(r"^[a-z][a-z0-9_]{1,80}$")
TABLE = re.compile(r"^[a-z][a-z0-9_.]{1,120}$")
CAPTURE = re.compile(r"^[a-f0-9]{32}$")
PII_NAME = re.compile(r"(e_?mail|phone|mobile|contact|address|street|tax_?code|cccd|cmnd|passport|id_card|birth|dob|full_name|first_name|last_name|customer_name|^name$|note|ho_ten|dien_thoai|so_dt|dia_chi|ngay_sinh)", re.I)
NUMERIC = re.compile(r"^(Nullable\()?(U?Int|Float|Decimal)")
MAX_COLUMNS = 80
LIMITS = "SETTINGS max_execution_time = 15, max_result_rows = 1000, readonly = 2"
MASK = "•••"


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


def _profile_sync(connection_id: str, table: str, capture_id: str | None) -> dict[str, Any]:
    client = ClickHouseClient()
    reference, columns = _resolve(client, connection_id, table)
    has_capture = "capture_id" in {column["name"] for column in columns}
    if capture_id is not None and not CAPTURE.fullmatch(capture_id):
        raise ValueError("capture_id is invalid")
    if capture_id is not None and not has_capture:
        raise ValueError("This raw table cannot be filtered by capture_id")
    if has_capture and capture_id is None:
        capture_id = client.scalar(f"SELECT capture_id FROM {reference} WHERE capture_id IS NOT NULL ORDER BY _dlt_load_id DESC LIMIT 1")
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
    return {"connection_id": connection_id, "table": table, "stream": _stream(table.replace(".", "__")), "rows": total_rows, "columns": masked_columns, "sample": rows}


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


__all__ = ["ClickHouseError", "get_masked_sample", "get_overview", "get_run", "list_assets", "run", "seed_demo"]
