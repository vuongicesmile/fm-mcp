"""Pydantic schemas for workflow tools."""
"""Pydantic v2 contracts for workflow and request APIs."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    step_order: int
    name: str
    approver_role: str
    approval_mode: str
    due_days: int | None
    conditions: dict


class WorkflowDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    description: str | None
    version: int
    is_active: bool
    steps: list[WorkflowStepRead] = []


class RequestCreate(BaseModel):
    workflow_definition_id: UUID
    request_type: str = Field(max_length=50)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    priority: str = "medium"
    department_id: str | None = Field(default=None, max_length=100)
    campus_id: str | None = Field(default=None, max_length=100)
    estimated_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    due_at: datetime | None = None


class RequestUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    priority: str | None = None
    department_id: str | None = Field(default=None, max_length=100)
    campus_id: str | None = Field(default=None, max_length=100)
    estimated_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    due_at: datetime | None = None


class RequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_code: str
    workflow_definition_id: UUID
    request_type: str
    title: str
    description: str | None
    status: str
    priority: str
    requester_id: str
    department_id: str | None
    campus_id: str | None
    estimated_value: Decimal | None
    currency: str | None
    due_at: datetime | None
    submitted_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RequestStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID
    from_status: str | None
    to_status: str
    changed_by: str
    comment: str | None
    changed_at: datetime
