"""Create attachment and immutable audit-log tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e3s005_supporting"
down_revision = "e3n004_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("fm_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("request_id", postgresql.UUID(as_uuid=True)),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True)), sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False), sa.Column("content_type", sa.String(150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False), sa.Column("uploaded_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_id"], ["fm_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["risk_id"], ["fm_risks.id"], ondelete="CASCADE"),
        sa.CheckConstraint("(request_id IS NOT NULL) OR (risk_id IS NOT NULL)", name="ck_fm_attachments_parent_required"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_fm_attachments_size_bytes"))
    op.create_index("ix_fm_attachments_request_created_at", "fm_attachments", ["request_id", "created_at"])
    op.create_index("ix_fm_attachments_risk_created_at", "fm_attachments", ["risk_id", "created_at"])
    op.create_table("fm_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("action", sa.String(80), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False), sa.Column("request_id", postgresql.UUID(as_uuid=True)),
        sa.Column("before_data", postgresql.JSONB()), sa.Column("after_data", postgresql.JSONB()),
        sa.Column("correlation_id", sa.String(100)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_id"], ["fm_requests.id"], ondelete="SET NULL"))
    op.create_index("ix_fm_audit_logs_entity_created_at", "fm_audit_logs", ["entity_type", "entity_id", "created_at"])
    op.create_index("ix_fm_audit_logs_request_created_at", "fm_audit_logs", ["request_id", "created_at"])


def downgrade() -> None:
    op.drop_table("fm_audit_logs")
    op.drop_table("fm_attachments")
