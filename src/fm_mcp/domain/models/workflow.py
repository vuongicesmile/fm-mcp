"""SQLAlchemy 2.x models owned by the EPIC 3 Workflow Automation module."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fm_mcp.infrastructure.database import Base


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UpdatedAtMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WorkflowDefinition(UpdatedAtMixin, Base):
    __tablename__ = "fm_workflow_definitions"
    __table_args__ = (UniqueConstraint("code", "version", name="uq_fm_workflow_definitions_code_version"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))

    steps: Mapped[list[WorkflowStep]] = relationship(
        back_populates="workflow_definition", cascade="all, delete-orphan", order_by="WorkflowStep.step_order"
    )
    requests: Mapped[list[FMRequest]] = relationship(back_populates="workflow_definition")
    escalation_rules: Mapped[list[EscalationRule]] = relationship(back_populates="workflow_definition")


class WorkflowStep(CreatedAtMixin, Base):
    __tablename__ = "fm_workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_definition_id", "step_order", name="uq_fm_workflow_steps_order"),
        CheckConstraint("step_order > 0", name="ck_fm_workflow_steps_order_positive"),
        CheckConstraint("approval_mode IN ('any', 'all')", name="ck_fm_workflow_steps_approval_mode"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("fm_workflow_definitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    approver_role: Mapped[str] = mapped_column(String(100), nullable=False)
    approval_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="any", server_default=text("'any'")
    )
    due_days: Mapped[int | None] = mapped_column(Integer)
    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    workflow_definition: Mapped[WorkflowDefinition] = relationship(back_populates="steps")
    approval_steps: Mapped[list[ApprovalStep]] = relationship(back_populates="workflow_step")
    escalation_rules: Mapped[list[EscalationRule]] = relationship(back_populates="workflow_step")


class FMRequest(UpdatedAtMixin, Base):
    __tablename__ = "fm_requests"
    __table_args__ = (
        UniqueConstraint("request_code", name="uq_fm_requests_request_code"),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'in_review', 'approved', 'rejected', 'returned', 'closed')",
            name="ck_fm_requests_status",
        ),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name="ck_fm_requests_priority"),
        Index("ix_fm_requests_status_created_at", "status", "created_at"),
        Index("ix_fm_requests_requester_created_at", "requester_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    request_code: Mapped[str] = mapped_column(String(50), nullable=False)
    workflow_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("fm_workflow_definitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft", server_default=text("'draft'")
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium", server_default=text("'medium'")
    )
    requester_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    department_id: Mapped[str | None] = mapped_column(String(100), index=True)
    campus_id: Mapped[str | None] = mapped_column(String(100), index=True)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    workflow_definition: Mapped[WorkflowDefinition] = relationship(back_populates="requests")
    status_history: Mapped[list[RequestStatusHistory]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="RequestStatusHistory.changed_at"
    )
    approval_steps: Mapped[list[ApprovalStep]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="ApprovalStep.step_order"
    )
    risks: Mapped[list[Risk]] = relationship(back_populates="request")
    notifications: Mapped[list[Notification]] = relationship(back_populates="request")
    reminders: Mapped[list[Reminder]] = relationship(back_populates="request")
    attachments: Mapped[list[Attachment]] = relationship(back_populates="request")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="request")


class RequestStatusHistory(Base):
    __tablename__ = "fm_request_status_history"
    __table_args__ = (Index("ix_fm_request_status_history_request_changed", "request_id", "changed_at"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("fm_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(100), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    request: Mapped[FMRequest] = relationship(back_populates="status_history")


class ApprovalStep(CreatedAtMixin, Base):
    __tablename__ = "fm_approval_steps"
    __table_args__ = (
        UniqueConstraint("request_id", "step_order", name="uq_fm_approval_steps_request_order"),
        CheckConstraint(
            "approval_mode IN ('any', 'all')", name="ck_fm_approval_steps_approval_mode"
        ),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'approved', 'rejected', 'returned', 'skipped')",
            name="ck_fm_approval_steps_status",
        ),
        Index("ix_fm_approval_steps_request_status", "request_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("fm_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_step_id: Mapped[UUID] = mapped_column(
        ForeignKey("fm_workflow_steps.id", ondelete="RESTRICT"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_id: Mapped[str | None] = mapped_column(String(100), index=True)
    approver_role: Mapped[str] = mapped_column(String(100), nullable=False)
    approval_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default=text("'pending'")
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    request: Mapped[FMRequest] = relationship(back_populates="approval_steps")
    workflow_step: Mapped[WorkflowStep] = relationship(back_populates="approval_steps")
    assignments: Mapped[list[ApprovalAssignment]] = relationship(
        back_populates="approval_step", cascade="all, delete-orphan"
    )
    actions: Mapped[list[ApprovalAction]] = relationship(
        back_populates="approval_step", cascade="all, delete-orphan"
    )
    reminders: Mapped[list[Reminder]] = relationship(back_populates="approval_step")


class ApprovalAssignment(CreatedAtMixin, Base):
    __tablename__ = "fm_approval_assignments"
    __table_args__ = (
        UniqueConstraint("approval_step_id", "approver_id", name="uq_fm_approval_assignments_step_approver"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'returned', 'skipped')",
            name="ck_fm_approval_assignments_status",
        ),
        Index("ix_fm_approval_assignments_approver_status", "approver_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    approval_step_id: Mapped[UUID] = mapped_column(
        ForeignKey("fm_approval_steps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approver_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default=text("'pending'")
    )
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    approval_step: Mapped[ApprovalStep] = relationship(back_populates="assignments")
    actions: Mapped[list[ApprovalAction]] = relationship(back_populates="approval_assignment")


class ApprovalAction(Base):
    __tablename__ = "fm_approval_actions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_fm_approval_actions_idempotency_key"),
        CheckConstraint(
            "action IN ('approve', 'reject', 'return')", name="ck_fm_approval_actions_action"
        ),
        Index("ix_fm_approval_actions_step_acted_at", "approval_step_id", "acted_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    approval_step_id: Mapped[UUID] = mapped_column(
        ForeignKey("fm_approval_steps.id", ondelete="CASCADE"), nullable=False
    )
    approval_assignment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fm_approval_assignments.id", ondelete="SET NULL")
    )
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    acted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)

    approval_step: Mapped[ApprovalStep] = relationship(back_populates="actions")
    approval_assignment: Mapped[ApprovalAssignment | None] = relationship(back_populates="actions")


class Risk(UpdatedAtMixin, Base):
    __tablename__ = "fm_risks"
    __table_args__ = (
        UniqueConstraint("risk_code", name="uq_fm_risks_risk_code"),
        CheckConstraint(
            "status IN ('open', 'mitigating', 'mitigated', 'accepted', 'closed')",
            name="ck_fm_risks_status",
        ),
        Index("ix_fm_risks_status_review_date", "status", "review_date"),
        Index("ix_fm_risks_owner_status", "owner_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    risk_code: Mapped[str] = mapped_column(String(50), nullable=False)
    request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fm_requests.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    owner_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="open", server_default=text("'open'")
    )
    mitigation_plan: Mapped[str | None] = mapped_column(Text)
    review_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    request: Mapped[FMRequest | None] = relationship(back_populates="risks")
    assessments: Mapped[list[RiskAssessment]] = relationship(
        back_populates="risk", cascade="all, delete-orphan", order_by="RiskAssessment.assessed_at"
    )
    attachments: Mapped[list[Attachment]] = relationship(back_populates="risk")


class RiskAssessment(Base):
    __tablename__ = "fm_risk_assessments"
    __table_args__ = (
        CheckConstraint("likelihood BETWEEN 1 AND 5", name="ck_fm_risk_assessments_likelihood"),
        CheckConstraint("impact BETWEEN 1 AND 5", name="ck_fm_risk_assessments_impact"),
        CheckConstraint("risk_score BETWEEN 1 AND 25", name="ck_fm_risk_assessments_score"),
        Index("ix_fm_risk_assessments_risk_assessed_at", "risk_id", "assessed_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    risk_id: Mapped[UUID] = mapped_column(
        ForeignKey("fm_risks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    likelihood: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    impact: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    risk_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    assessment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    assessed_by: Mapped[str] = mapped_column(String(100), nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    risk: Mapped[Risk] = relationship(back_populates="assessments")


class NotificationTemplate(UpdatedAtMixin, Base):
    __tablename__ = "fm_notification_templates"
    __table_args__ = (
        UniqueConstraint("event_code", "channel", name="uq_fm_notification_templates_event_channel"),
        CheckConstraint("channel IN ('email', 'teams', 'in_app')", name="ck_fm_notification_templates_channel"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    event_code: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_template: Mapped[str | None] = mapped_column(Text)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))

    notifications: Mapped[list[Notification]] = relationship(back_populates="template")


class Notification(CreatedAtMixin, Base):
    __tablename__ = "fm_notifications"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'teams', 'in_app')", name="ck_fm_notifications_channel"),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'cancelled')",
            name="ck_fm_notifications_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_fm_notifications_attempt_count"),
        Index("ix_fm_notifications_status_scheduled_at", "status", "scheduled_at"),
        Index("ix_fm_notifications_recipient_created_at", "recipient_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fm_requests.id", ondelete="SET NULL"), index=True
    )
    template_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fm_notification_templates.id", ondelete="SET NULL")
    )
    recipient_id: Mapped[str] = mapped_column(String(100), nullable=False)
    recipient_address: Mapped[str | None] = mapped_column(String(320))
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    event_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default=text("'pending'")
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    request: Mapped[FMRequest | None] = relationship(back_populates="notifications")
    template: Mapped[NotificationTemplate | None] = relationship(back_populates="notifications")
    reminders: Mapped[list[Reminder]] = relationship(back_populates="notification")


class EscalationRule(CreatedAtMixin, Base):
    __tablename__ = "fm_escalation_rules"
    __table_args__ = (
        CheckConstraint("offset_minutes >= 0", name="ck_fm_escalation_rules_offset_minutes"),
        CheckConstraint("channel IN ('email', 'teams', 'in_app')", name="ck_fm_escalation_rules_channel"),
        Index("ix_fm_escalation_rules_workflow_enabled", "workflow_definition_id", "enabled"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("fm_workflow_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    workflow_step_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fm_workflow_steps.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(40), nullable=False)
    offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    target_role: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))

    workflow_definition: Mapped[WorkflowDefinition] = relationship(back_populates="escalation_rules")
    workflow_step: Mapped[WorkflowStep | None] = relationship(back_populates="escalation_rules")
    reminders: Mapped[list[Reminder]] = relationship(back_populates="rule")


class Reminder(CreatedAtMixin, Base):
    __tablename__ = "fm_reminders"
    __table_args__ = (
        UniqueConstraint("approval_step_id", "rule_id", "scheduled_at", name="uq_fm_reminders_step_rule_schedule"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'processed', 'failed', 'cancelled')",
            name="ck_fm_reminders_status",
        ),
        Index("ix_fm_reminders_status_scheduled_at", "status", "scheduled_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("fm_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approval_step_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fm_approval_steps.id", ondelete="SET NULL"), index=True
    )
    rule_id: Mapped[UUID] = mapped_column(
        ForeignKey("fm_escalation_rules.id", ondelete="RESTRICT"), nullable=False
    )
    notification_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fm_notifications.id", ondelete="SET NULL")
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default=text("'pending'")
    )

    request: Mapped[FMRequest] = relationship(back_populates="reminders")
    approval_step: Mapped[ApprovalStep | None] = relationship(back_populates="reminders")
    rule: Mapped[EscalationRule] = relationship(back_populates="reminders")
    notification: Mapped[Notification | None] = relationship(back_populates="reminders")


class Attachment(CreatedAtMixin, Base):
    __tablename__ = "fm_attachments"
    __table_args__ = (
        CheckConstraint(
            "(request_id IS NOT NULL) OR (risk_id IS NOT NULL)", name="ck_fm_attachments_parent_required"
        ),
        CheckConstraint("size_bytes >= 0", name="ck_fm_attachments_size_bytes"),
        Index("ix_fm_attachments_request_created_at", "request_id", "created_at"),
        Index("ix_fm_attachments_risk_created_at", "risk_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID | None] = mapped_column(ForeignKey("fm_requests.id", ondelete="CASCADE"))
    risk_id: Mapped[UUID | None] = mapped_column(ForeignKey("fm_risks.id", ondelete="CASCADE"))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(100), nullable=False)

    request: Mapped[FMRequest | None] = relationship(back_populates="attachments")
    risk: Mapped[Risk | None] = relationship(back_populates="attachments")


class AuditLog(CreatedAtMixin, Base):
    __tablename__ = "fm_audit_logs"
    __table_args__ = (
        Index("ix_fm_audit_logs_entity_created_at", "entity_type", "entity_id", "created_at"),
        Index("ix_fm_audit_logs_request_created_at", "request_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fm_requests.id", ondelete="SET NULL"), index=True
    )
    before_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    correlation_id: Mapped[str | None] = mapped_column(String(100), index=True)

    request: Mapped[FMRequest | None] = relationship(back_populates="audit_logs")
