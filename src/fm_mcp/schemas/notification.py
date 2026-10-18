"""Pydantic schemas for notification tools."""
"""Pydantic v2 contracts for notification and escalation read APIs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID | None
    recipient_id: str
    channel: str
    event_code: str
    status: str
    attempt_count: int
    scheduled_at: datetime
    sent_at: datetime | None


class EscalationRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workflow_definition_id: UUID
    workflow_step_id: UUID | None
    name: str
    trigger_type: str
    offset_minutes: int
    target_role: str
    channel: str
    enabled: bool


class ReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID
    approval_step_id: UUID | None
    rule_id: UUID
    scheduled_at: datetime
    processed_at: datetime | None
    status: str


class NotificationTemplateCreate(BaseModel):
    event_code: str
    channel: str
    subject_template: str | None = None
    body_template: str
    is_active: bool = True


class NotificationTemplateUpdate(BaseModel):
    subject_template: str | None = None
    body_template: str | None = None
    is_active: bool | None = None


class NotificationTemplateRead(NotificationTemplateCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationRead]
    total: int
    offset: int
    limit: int
