"""Pydantic schemas for workflow tools."""
"""Pydantic v2 contracts for workflow and request APIs."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
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
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    context: dict = Field(default_factory=dict)
    department_id: str | None = Field(default=None, max_length=100)
    campus_id: str | None = Field(default=None, max_length=100)
    estimated_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    due_at: datetime | None = None


class RequestUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    priority: Literal["low", "medium", "high", "critical"] | None = None
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
    context: dict
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


class WorkflowStepCreate(BaseModel):
    step_order: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    approver_role: str = Field(min_length=1, max_length=100)
    approval_mode: Literal["any", "all"] = "any"
    due_days: int | None = Field(default=None, ge=0)
    conditions: dict = Field(default_factory=dict)


class WorkflowStepUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    approver_role: str | None = Field(default=None, min_length=1, max_length=100)
    approval_mode: Literal["any", "all"] | None = None
    due_days: int | None = Field(default=None, ge=0)
    conditions: dict | None = None


class WorkflowDefinitionCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    version: int = Field(default=1, ge=1)
    is_active: bool = True
    steps: list[WorkflowStepCreate] = Field(default_factory=list)


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None


class RequestList(BaseModel):
    items: list[RequestRead]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
