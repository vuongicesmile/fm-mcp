"""Persistence and overview aggregation for FM-owned profiling runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from fm_mcp.domain.models.profiling import DataProfileRun
from fm_mcp.infrastructure.database import SessionLocal


def serialize(row: DataProfileRun) -> dict[str, Any]:
    return {
        "id": row.id.hex,
        "connection_id": row.connection_id,
        "table": row.table_name,
        "capture_id": row.capture_id,
        "result": row.result,
        "created_at": row.created_at.isoformat(),
    }


async def create(
    *, tenant_id: str, connection_id: str, table: str, capture_id: str | None,
    result: dict[str, Any], is_demo: bool = False,
) -> dict[str, Any]:
    async with SessionLocal() as session:
        row = DataProfileRun(
            tenant_id=tenant_id,
            connection_id=connection_id,
            table_name=table,
            capture_id=capture_id,
            layer=str(result.get("layer", "bronze")),
            is_demo=is_demo,
            result=result,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return serialize(row)


async def get(tenant_id: str, run_id: str) -> dict[str, Any]:
    try:
        key = UUID(hex=run_id)
    except ValueError as exc:
        raise ValueError("run_id must be a 32-character lowercase identifier") from exc
    async with SessionLocal() as session:
        row = await session.scalar(
            select(DataProfileRun).where(DataProfileRun.id == key, DataProfileRun.tenant_id == tenant_id)
        )
    if row is None:
        raise ValueError("Data-profiling run was not found")
    return serialize(row)


def _status_counts(runs: list[dict[str, Any]]) -> dict[str, int]:
    return {status: sum(1 for run in runs if run["result"].get("status") == status) for status in ("pass", "warn", "fail")}


def _dimension_overview(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[float]] = {}
    for run in runs:
        for key, value in (run["result"].get("dimensions") or {}).items():
            if isinstance(value, dict) and isinstance(value.get("score"), (int, float)):
                buckets.setdefault(key, []).append(float(value["score"]))
    return [
        {"key": key, "score": round(sum(scores) / len(scores), 1), "assets": len(scores)}
        for key, scores in sorted(buckets.items())
    ]


async def overview(
    tenant_id: str, *, layer: str = "bronze", year: int | None = None,
    month: int | None = None, include_demo: bool = False,
) -> dict[str, Any]:
    statement = select(DataProfileRun).where(
        DataProfileRun.tenant_id == tenant_id, DataProfileRun.layer == layer
    ).order_by(DataProfileRun.created_at.desc()).limit(500)
    if not include_demo:
        statement = statement.where(DataProfileRun.is_demo.is_(False))
    async with SessionLocal() as session:
        rows = list((await session.scalars(statement)).all())
    runs = [serialize(row) for row in rows]
    if year is not None:
        runs = [run for run in runs if datetime.fromisoformat(run["created_at"]).year == year]
    if month is not None:
        runs = [run for run in runs if datetime.fromisoformat(run["created_at"]).month == month]

    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for run in runs:
        latest.setdefault((run["connection_id"], run["table"]), run)
    assets = list(latest.values())
    total_rows = sum(int(run["result"].get("rows", 0)) for run in assets)
    scores = [float(run["result"].get("quality_score", 0)) for run in assets]
    return {
        "layer": layer,
        "filters": {"year": year, "month": month, "include_demo": include_demo},
        "totals": {
            "assets": len(assets), "profiled_rows": total_rows,
            "quality_score": round(sum(scores) / len(scores), 1) if scores else None,
            "statuses": _status_counts(assets),
        },
        "dimensions": _dimension_overview(assets),
        "assets": assets,
        "runs": runs[:100],
    }
