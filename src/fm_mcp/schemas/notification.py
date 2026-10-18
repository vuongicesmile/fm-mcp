"""Pydantic schemas for notification tools."""
"""Pydantic v2 contracts for notification and escalation read APIs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID | None
    recipient_id: str
    recipient_address: str | None
    channel: str
    event_code: str
    status: str
    attempt_count: int
    last_error: str | None
    payload: dict
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
    created_at: datetime


class ReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID
    approval_step_id: UUID | None
    rule_id: UUID
    scheduled_at: datetime
    processed_at: datetime | None
    status: str
    notification_id: UUID | None


class NotificationTemplateCreate(BaseModel):
    event_code: str = Field(min_length=1, max_length=80)
    channel: str = Field(pattern="^(email|teams|in_app)$")
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


class NotificationCreate(BaseModel):
    request_id: UUID | None = None
    recipient_id: str = Field(min_length=1, max_length=100)
    recipient_address: str | None = Field(default=None, max_length=320)
    channel: str = Field(pattern="^(email|teams|in_app)$")
    event_code: str = Field(min_length=1, max_length=80)
    payload: dict = Field(default_factory=dict)
    scheduled_at: datetime | None = None

    @model_validator(mode="after")
    def require_email_address(self) -> "NotificationCreate":
        if self.channel == "email" and not self.recipient_address:
            raise ValueError("recipient_address is required for email notifications")
        return self


class EscalationRuleCreate(BaseModel):
    workflow_definition_id: UUID
    workflow_step_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    trigger_type: str = Field(min_length=1, max_length=40)
    offset_minutes: int = Field(ge=0)
    target_role: str = Field(min_length=1, max_length=100)
    channel: str = Field(pattern="^(email|teams|in_app)$")
    enabled: bool = True


class EscalationRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    offset_minutes: int | None = Field(default=None, ge=0)
    target_role: str | None = Field(default=None, min_length=1, max_length=100)
    channel: str | None = Field(default=None, pattern="^(email|teams|in_app)$")
    enabled: bool | None = None
