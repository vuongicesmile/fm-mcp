"""Transactional workflow/request application service."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fm_mcp.domain.models.workflow import (
    ApprovalStep,
    AuditLog,
    FMRequest,
    RequestStatusHistory,
    WorkflowDefinition,
)
from fm_mcp.schemas.workflow import RequestCreate, RequestUpdate


class WorkflowService:
    def __init__(self, session: AsyncSession, actor_id: str) -> None:
        self.session = session
        self.actor_id = actor_id

    async def create_request(self, data: RequestCreate) -> FMRequest:
        workflow = await self.session.scalar(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == data.workflow_definition_id,
                WorkflowDefinition.is_active.is_(True),
            )
        )
        if workflow is None:
            raise HTTPException(status_code=404, detail="Active workflow definition not found")
        request = FMRequest(
            request_code=f"REQ-{uuid4().hex[:12].upper()}",
            workflow_definition_id=data.workflow_definition_id,
            request_type=data.request_type,
            title=data.title,
            description=data.description,
            priority=data.priority,
            requester_id=self.actor_id,
            department_id=data.department_id,
            campus_id=data.campus_id,
            estimated_value=data.estimated_value,
            currency=data.currency,
            due_at=data.due_at,
        )
        self.session.add(request)
        await self.session.flush()
        self.session.add(RequestStatusHistory(request_id=request.id, to_status="draft", changed_by=self.actor_id))
        self.session.add(AuditLog(entity_type="request", entity_id=request.id, action="created", actor_id=self.actor_id, request_id=request.id))
        return request

    async def get_request(self, request_id: UUID, lock: bool = False) -> FMRequest:
        statement = select(FMRequest).where(FMRequest.id == request_id)
        if lock:
            statement = statement.with_for_update()
        request = await self.session.scalar(statement)
        if request is None:
            raise HTTPException(status_code=404, detail="Request not found")
        return request

    async def update_draft(self, request_id: UUID, data: RequestUpdate) -> FMRequest:
        request = await self.get_request(request_id, lock=True)
        if request.requester_id != self.actor_id:
            raise HTTPException(status_code=403, detail="Only the requester may update this request")
        if request.status not in {"draft", "returned"}:
            raise HTTPException(status_code=409, detail="Only draft or returned requests can be updated")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(request, field, value)
        self.session.add(AuditLog(entity_type="request", entity_id=request.id, action="updated", actor_id=self.actor_id, request_id=request.id))
        return request

    async def submit(self, request_id: UUID) -> FMRequest:
        request = await self.get_request(request_id, lock=True)
        if request.requester_id != self.actor_id:
            raise HTTPException(status_code=403, detail="Only the requester may submit this request")
        if request.status not in {"draft", "returned"}:
            raise HTTPException(status_code=409, detail="Request cannot be submitted")
        workflow = await self.session.scalar(
            select(WorkflowDefinition).options(selectinload(WorkflowDefinition.steps)).where(
                WorkflowDefinition.id == request.workflow_definition_id
            )
        )
        if workflow is None or not workflow.steps:
            raise HTTPException(status_code=409, detail="Workflow has no approval steps")
        request.status = "in_review"
        request.submitted_at = datetime.now(UTC)
        for step in workflow.steps:
            self.session.add(ApprovalStep(
                request_id=request.id, workflow_step_id=step.id, step_order=step.step_order,
                approver_role=step.approver_role, approval_mode=step.approval_mode,
                due_at=(request.submitted_at if step.due_days is None else None),
            ))
        self.session.add(RequestStatusHistory(request_id=request.id, from_status="draft", to_status="in_review", changed_by=self.actor_id))
        self.session.add(AuditLog(entity_type="request", entity_id=request.id, action="submitted", actor_id=self.actor_id, request_id=request.id))
        return request

    async def close(self, request_id: UUID) -> FMRequest:
        request = await self.get_request(request_id, lock=True)
        if request.requester_id != self.actor_id:
            raise HTTPException(status_code=403, detail="Only the requester may close this request")
        if request.status != "approved":
            raise HTTPException(status_code=409, detail="Only approved requests can be closed")
        request.status, request.closed_at = "closed", datetime.now(UTC)
        self.session.add(RequestStatusHistory(request_id=request.id, from_status="approved", to_status="closed", changed_by=self.actor_id))
        self.session.add(AuditLog(entity_type="request", entity_id=request.id, action="closed", actor_id=self.actor_id, request_id=request.id))
        return request
