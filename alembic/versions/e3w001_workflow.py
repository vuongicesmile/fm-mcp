"""Create workflow definitions, steps, requests and history."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e3w001_workflow"
down_revision = None
branch_labels = ("workflow_automation",)
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fm_workflow_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", "version", name="uq_fm_workflow_definitions_code_version"),
    )
    op.create_table(
        "fm_workflow_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("approver_role", sa.String(100), nullable=False),
        sa.Column("approval_mode", sa.String(20), nullable=False, server_default="any"),
        sa.Column("due_days", sa.Integer()),
        sa.Column("conditions", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workflow_definition_id"], ["fm_workflow_definitions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("workflow_definition_id", "step_order", name="uq_fm_workflow_steps_order"),
        sa.CheckConstraint("step_order > 0", name="ck_fm_workflow_steps_order_positive"),
        sa.CheckConstraint("approval_mode IN ('any', 'all')", name="ck_fm_workflow_steps_approval_mode"),
    )
    op.create_index("ix_fm_workflow_steps_workflow_definition_id", "fm_workflow_steps", ["workflow_definition_id"])
    op.create_table(
        "fm_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_code", sa.String(50), nullable=False),
        sa.Column("workflow_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("requester_id", sa.String(100), nullable=False),
        sa.Column("department_id", sa.String(100)),
        sa.Column("campus_id", sa.String(100)),
        sa.Column("estimated_value", sa.Numeric(18, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workflow_definition_id"], ["fm_workflow_definitions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("request_code", name="uq_fm_requests_request_code"),
        sa.CheckConstraint("status IN ('draft', 'submitted', 'in_review', 'approved', 'rejected', 'returned', 'closed')", name="ck_fm_requests_status"),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name="ck_fm_requests_priority"),
    )
    for name, columns in (
        ("ix_fm_requests_workflow_definition_id", ["workflow_definition_id"]),
        ("ix_fm_requests_status_created_at", ["status", "created_at"]),
        ("ix_fm_requests_requester_created_at", ["requester_id", "created_at"]),
    ):
        op.create_index(name, "fm_requests", columns)
    op.create_table(
        "fm_request_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_status", sa.String(30)),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("changed_by", sa.String(100), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_id"], ["fm_requests.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_fm_request_status_history_request_changed", "fm_request_status_history", ["request_id", "changed_at"])


def downgrade() -> None:
    op.drop_table("fm_request_status_history")
    op.drop_table("fm_requests")
    op.drop_table("fm_workflow_steps")
    op.drop_table("fm_workflow_definitions")
