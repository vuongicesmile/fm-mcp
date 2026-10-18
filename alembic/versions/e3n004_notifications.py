"""Create notification, escalation and reminder tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e3n004_notifications"
down_revision = "e3r003_risks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("fm_notification_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("event_code", sa.String(80), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False), sa.Column("subject_template", sa.Text()),
        sa.Column("body_template", sa.Text(), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("event_code", "channel", name="uq_fm_notification_templates_event_channel"),
        sa.CheckConstraint("channel IN ('email', 'teams', 'in_app')", name="ck_fm_notification_templates_channel"))
    op.create_table("fm_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("request_id", postgresql.UUID(as_uuid=True)),
        sa.Column("template_id", postgresql.UUID(as_uuid=True)), sa.Column("recipient_id", sa.String(100), nullable=False),
        sa.Column("recipient_address", sa.String(320)), sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("event_code", sa.String(80), nullable=False), sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"), sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()), sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_id"], ["fm_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["fm_notification_templates.id"], ondelete="SET NULL"),
        sa.CheckConstraint("channel IN ('email', 'teams', 'in_app')", name="ck_fm_notifications_channel"),
        sa.CheckConstraint("status IN ('pending', 'sending', 'sent', 'failed', 'cancelled')", name="ck_fm_notifications_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_fm_notifications_attempt_count"))
    op.create_index("ix_fm_notifications_status_scheduled_at", "fm_notifications", ["status", "scheduled_at"])
    op.create_table("fm_escalation_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("workflow_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_step_id", postgresql.UUID(as_uuid=True)), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("trigger_type", sa.String(40), nullable=False), sa.Column("offset_minutes", sa.Integer(), nullable=False),
        sa.Column("target_role", sa.String(100), nullable=False), sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workflow_definition_id"], ["fm_workflow_definitions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workflow_step_id"], ["fm_workflow_steps.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("offset_minutes >= 0", name="ck_fm_escalation_rules_offset_minutes"),
        sa.CheckConstraint("channel IN ('email', 'teams', 'in_app')", name="ck_fm_escalation_rules_channel"))
    op.create_table("fm_reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_step_id", postgresql.UUID(as_uuid=True)), sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True)), sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)), sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_id"], ["fm_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_step_id"], ["fm_approval_steps.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rule_id"], ["fm_escalation_rules.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["notification_id"], ["fm_notifications.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("approval_step_id", "rule_id", "scheduled_at", name="uq_fm_reminders_step_rule_schedule"),
        sa.CheckConstraint("status IN ('pending', 'processing', 'processed', 'failed', 'cancelled')", name="ck_fm_reminders_status"))
    op.create_index("ix_fm_reminders_status_scheduled_at", "fm_reminders", ["status", "scheduled_at"])


def downgrade() -> None:
    op.drop_table("fm_reminders")
    op.drop_table("fm_escalation_rules")
    op.drop_table("fm_notifications")
    op.drop_table("fm_notification_templates")
