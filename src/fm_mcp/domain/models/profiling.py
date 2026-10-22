"""Persistent records owned by the FM data-profiling domain."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from fm_mcp.domain.models.workflow import CreatedAtMixin
from fm_mcp.infrastructure.database import Base


class DataProfileRun(CreatedAtMixin, Base):
    """One immutable quality assessment returned by an FM MCP tool."""

    __tablename__ = "fm_data_profile_runs"
    __table_args__ = (
        Index("ix_fm_data_profile_runs_tenant_layer_created", "tenant_id", "layer", "created_at"),
        Index("ix_fm_data_profile_runs_tenant_asset_created", "tenant_id", "connection_id", "table_name", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(30), nullable=False)
    connection_id: Mapped[str] = mapped_column(String(80), nullable=False)
    table_name: Mapped[str] = mapped_column(String(160), nullable=False)
    capture_id: Mapped[str | None] = mapped_column(String(32))
    layer: Mapped[str] = mapped_column(String(16), nullable=False, default="bronze")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
