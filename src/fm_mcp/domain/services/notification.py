"""Notification persistence and idempotent escalation scheduling.

Delivery is intentionally outside this module: an existing mail/Teams adapter can claim
pending records and update delivery status. This avoids pretending database commits are
external delivery guarantees when no transactional outbox exists yet.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from fm_mcp.domain.models.workflow import (
    ApprovalAssignment,
    ApprovalStep,
    AuditLog,
    EscalationRule,
    FMRequest,
    Notification,
    NotificationTemplate,
    Reminder,
    WorkflowDefinition,
    WorkflowStep,
)
from fm_mcp.schemas.notification import EscalationRuleCreate, EscalationRuleUpdate, NotificationCreate, NotificationTemplateCreate, NotificationTemplateUpdate


class NotificationService:
    def __init__(self, session: AsyncSession, actor_id: str, roles: frozenset[str]) -> None:
        self.session, self.actor_id, self.roles = session, actor_id, roles

    def _admin(self) -> None:
        if "fm_admin" not in self.roles:
            raise HTTPException(status_code=403, detail="FM admin role required")

    async def list_notifications(self, offset: int, limit: int, request_id: UUID | None) -> tuple[list[Notification], int]:
        filters = [Notification.recipient_id == self.actor_id]
        if "fm_admin" in self.roles:
            filters = []
        if request_id:
            filters.append(Notification.request_id == request_id)
        statement = select(Notification).where(*filters).order_by(Notification.created_at.desc())
        total = await self.session.scalar(select(func.count()).select_from(Notification).where(*filters))
        return list((await self.session.scalars(statement.offset(offset).limit(limit))).all()), total or 0

    async def queue(self, data: NotificationCreate) -> Notification:
        self._admin()
        if data.request_id and not await self.session.get(FMRequest, data.request_id):
            raise HTTPException(status_code=404, detail="Request not found")
        template = await self.session.scalar(select(NotificationTemplate).where(
            NotificationTemplate.event_code == data.event_code,
            NotificationTemplate.channel == data.channel,
            NotificationTemplate.is_active.is_(True),
        ))
        item = Notification(template_id=template.id if template else None, status="pending", **data.model_dump(exclude={"scheduled_at"}), scheduled_at=data.scheduled_at or datetime.now(UTC))
        self.session.add(item)
        await self.session.flush()
        return item

    async def create_template(self, data: NotificationTemplateCreate) -> NotificationTemplate:
        self._admin()
        template = NotificationTemplate(**data.model_dump())
        self.session.add(template)
        await self.session.flush()
        await self.session.refresh(template)
        return template

    async def update_template(self, template_id: UUID, data: NotificationTemplateUpdate) -> NotificationTemplate:
        self._admin()
        template = await self.session.scalar(select(NotificationTemplate).where(NotificationTemplate.id == template_id).with_for_update())
        if template is None:
            raise HTTPException(status_code=404, detail="Notification template not found")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(template, field, value)
        await self.session.flush()
        await self.session.refresh(template)
        return template

    async def create_rule(self, data: EscalationRuleCreate) -> EscalationRule:
        self._admin()
        workflow = await self.session.get(WorkflowDefinition, data.workflow_definition_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow definition not found")
        if data.workflow_step_id:
            step = await self.session.get(WorkflowStep, data.workflow_step_id)
            if step is None or step.workflow_definition_id != data.workflow_definition_id:
                raise HTTPException(status_code=422, detail="Workflow step does not belong to workflow definition")
        rule = EscalationRule(**data.model_dump())
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def update_rule(self, rule_id: UUID, data: EscalationRuleUpdate) -> EscalationRule:
        self._admin()
        rule = await self.session.scalar(select(EscalationRule).where(EscalationRule.id == rule_id).with_for_update())
        if rule is None:
            raise HTTPException(status_code=404, detail="Escalation rule not found")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(rule, field, value)
        await self.session.flush()
        return rule

    async def overdue_requests(self, offset: int, limit: int) -> tuple[list[FMRequest], int]:
        self._admin()
        filters = [FMRequest.due_at.is_not(None), FMRequest.due_at < datetime.now(UTC), FMRequest.status.in_(("draft", "submitted", "in_review", "returned"))]
        statement = select(FMRequest).where(*filters).order_by(FMRequest.due_at).offset(offset).limit(limit)
        total = await self.session.scalar(select(func.count()).select_from(FMRequest).where(*filters))
        return list((await self.session.scalars(statement)).all()), total or 0

    async def evaluate_escalations(self, now: datetime | None = None) -> int:
        """Create at most one reminder for each due approval-step/rule/schedule tuple."""
        now = now or datetime.now(UTC)
        candidates = await self.session.execute(
            select(ApprovalStep, FMRequest, EscalationRule)
            .join(FMRequest, FMRequest.id == ApprovalStep.request_id)
            .join(EscalationRule, EscalationRule.workflow_definition_id == FMRequest.workflow_definition_id)
            .where(
                ApprovalStep.status.in_(("pending", "in_progress")), ApprovalStep.due_at.is_not(None),
                EscalationRule.enabled.is_(True),
                (EscalationRule.workflow_step_id.is_(None)) | (EscalationRule.workflow_step_id == ApprovalStep.workflow_step_id),
            )
        )
        created = 0
        for step, request, rule in candidates.all():
            scheduled_at = step.due_at + timedelta(minutes=rule.offset_minutes)
            if scheduled_at > now:
                continue
            reminder_id = await self.session.scalar(
                insert(Reminder).values(
                    request_id=request.id, approval_step_id=step.id, rule_id=rule.id,
                    scheduled_at=scheduled_at, status="pending",
                ).on_conflict_do_nothing(
                    constraint="uq_fm_reminders_step_rule_schedule"
                ).returning(Reminder.id)
            )
            if reminder_id is None:
                continue
            assignees = list((await self.session.scalars(
                select(ApprovalAssignment.approver_id).where(
                    ApprovalAssignment.approval_step_id == step.id,
                    ApprovalAssignment.status == "pending",
                )
            )).all())
            if assignees:
                notification = Notification(
                    request_id=request.id, recipient_id=assignees[0], channel=rule.channel,
                    event_code="approval_overdue", payload={"request_code": request.request_code, "approval_step_id": str(step.id)},
                )
                self.session.add(notification)
                await self.session.flush()
                reminder = await self.session.get(Reminder, reminder_id)
                if reminder:
                    reminder.notification_id = notification.id
            self.session.add(AuditLog(entity_type="approval_step", entity_id=step.id, action="reminder_created", actor_id="system", request_id=request.id))
            created += 1
        return created
