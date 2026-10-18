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


class ApprovalAssignmentCreate(BaseModel):
    approver_id: str = Field(min_length=1, max_length=100)


class ApprovalStepCreate(BaseModel):
    workflow_step_id: UUID
    step_order: int = Field(ge=1)
    approver_role: str = Field(min_length=1, max_length=100)
    approval_mode: str
    due_at: datetime | None = None
    assignments: list[ApprovalAssignmentCreate] = Field(default_factory=list)


class ApprovalList(BaseModel):
    items: list[ApprovalStepRead]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
