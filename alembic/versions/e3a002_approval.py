"""Create approval steps, assignments and actions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e3a002_approval"
down_revision = "e3w001_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("fm_approval_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_step_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False), sa.Column("approver_id", sa.String(100)),
        sa.Column("approver_role", sa.String(100), nullable=False), sa.Column("approval_mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("due_at", sa.DateTime(timezone=True)), sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_id"], ["fm_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_step_id"], ["fm_workflow_steps.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("request_id", "step_order", name="uq_fm_approval_steps_request_order"),
        sa.CheckConstraint("approval_mode IN ('any', 'all')", name="ck_fm_approval_steps_approval_mode"),
        sa.CheckConstraint("status IN ('pending', 'in_progress', 'approved', 'rejected', 'returned', 'skipped')", name="ck_fm_approval_steps_status"))
    op.create_index("ix_fm_approval_steps_request_status", "fm_approval_steps", ["request_id", "status"])
    op.create_table("fm_approval_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("approval_step_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_id", sa.String(100), nullable=False), sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("acted_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["approval_step_id"], ["fm_approval_steps.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("approval_step_id", "approver_id", name="uq_fm_approval_assignments_step_approver"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'returned', 'skipped')", name="ck_fm_approval_assignments_status"))
    op.create_index("ix_fm_approval_assignments_approver_status", "fm_approval_assignments", ["approver_id", "status"])
    op.create_table("fm_approval_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("approval_step_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_assignment_id", postgresql.UUID(as_uuid=True)), sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(30), nullable=False), sa.Column("comment", sa.Text()),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("idempotency_key", sa.String(100)),
        sa.ForeignKeyConstraint(["approval_step_id"], ["fm_approval_steps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_assignment_id"], ["fm_approval_assignments.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("idempotency_key", name="uq_fm_approval_actions_idempotency_key"),
        sa.CheckConstraint("action IN ('approve', 'reject', 'return')", name="ck_fm_approval_actions_action"))
    op.create_index("ix_fm_approval_actions_step_acted_at", "fm_approval_actions", ["approval_step_id", "acted_at"])


def downgrade() -> None:
    op.drop_table("fm_approval_actions")
    op.drop_table("fm_approval_assignments")
    op.drop_table("fm_approval_steps")
