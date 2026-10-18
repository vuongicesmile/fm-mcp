"""Pydantic schemas for approval tools."""
"""Pydantic v2 contracts for approval APIs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApprovalAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    approver_id: str
    status: str
    acted_at: datetime | None


class ApprovalStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID
    workflow_step_id: UUID
    step_order: int
    approver_role: str
    approval_mode: str
    status: str
    due_at: datetime | None
    assignments: list[ApprovalAssignmentRead] = []


class ApprovalActionCreate(BaseModel):
    comment: str | None = Field(default=None, max_length=4000)


class ApprovalActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    approval_step_id: UUID
    approval_assignment_id: UUID | None
    actor_id: str
    action: str
    comment: str | None
    acted_at: datetime
