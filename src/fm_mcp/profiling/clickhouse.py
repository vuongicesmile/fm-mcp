"""Small ClickHouse HTTP client used only by FM profiling tools."""

from __future__ import annotations

from typing import Any

import httpx

from fm_mcp.core.config import settings


class ClickHouseError(RuntimeError):
    """A safe operational error for a failed warehouse query."""


class ClickHouseClient:
    def __init__(self) -> None:
        self.url = settings.profiling_clickhouse_url.rstrip("/") + "/"
        self.auth = (settings.profiling_clickhouse_user, settings.profiling_clickhouse_password)

    def query_json(self, sql: str, *, parameters: dict[str, str] | None = None) -> list[dict[str, Any]]:
        params = {f"param_{key}": value for key, value in (parameters or {}).items()}
        try:
            response = httpx.post(
                self.url,
                content=(sql.rstrip().rstrip(";") + " FORMAT JSON").encode("utf-8"),
                params=params,
                auth=self.auth,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json().get("data", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise ClickHouseError("FM profiling cannot query the configured warehouse") from exc
        if not isinstance(data, list):
            raise ClickHouseError("Warehouse returned an invalid profiling response")
        return data

    def execute(self, sql: str, *, parameters: dict[str, str] | None = None) -> None:
        """Execute a development DDL/DML statement without appending a format clause."""
        params = {f"param_{key}": value for key, value in (parameters or {}).items()}
        try:
            response = httpx.post(
                self.url,
                content=sql.rstrip().rstrip(";").encode("utf-8"),
                params=params,
                auth=self.auth,
                timeout=30,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ClickHouseError("FM profiling cannot update the configured warehouse") from exc

    def scalar(self, sql: str, *, parameters: dict[str, str] | None = None) -> Any:
        rows = self.query_json(sql, parameters=parameters)
        return next(iter(rows[0].values()), None) if rows else None
