"""Create persistent FM MCP data-profiling runs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e3p007_data_profiling"
down_revision = "e3e006_request_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fm_data_profile_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(30), nullable=False),
        sa.Column("connection_id", sa.String(80), nullable=False),
        sa.Column("table_name", sa.String(160), nullable=False),
        sa.Column("capture_id", sa.String(32)),
        sa.Column("layer", sa.String(16), nullable=False, server_default="bronze"),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_fm_data_profile_runs_tenant_layer_created",
        "fm_data_profile_runs", ["tenant_id", "layer", "created_at"],
    )
    op.create_index(
        "ix_fm_data_profile_runs_tenant_asset_created",
        "fm_data_profile_runs", ["tenant_id", "connection_id", "table_name", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("fm_data_profile_runs")
