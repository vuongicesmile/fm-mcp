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
