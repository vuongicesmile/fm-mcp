"""Transactional workflow/request application service."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fm_mcp.domain.models.workflow import (
    ApprovalStep,
    ApprovalAssignment,
    AuditLog,
    FMRequest,
    Notification,
    RequestStatusHistory,
    WorkflowDefinition,
)
from fm_mcp.schemas.workflow import RequestCreate, RequestUpdate


class WorkflowService:
    """Xử lý lifecycle request; mọi write chạy trong transaction của router."""
    def __init__(self, session: AsyncSession, actor_id: str) -> None:
        self.session = session
        self.actor_id = actor_id

    async def create_request(self, data: RequestCreate) -> FMRequest:
        """Tạo draft do current user sở hữu, đồng thời ghi history và audit."""
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
            context=data.context,
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
        # Đồng bộ timestamp do PostgreSQL trigger duy trì trước khi Pydantic
        # đọc object ORM để tạo REST response.
        await self.session.flush()
        await self.session.refresh(request)
        return request

    async def get_request(self, request_id: UUID, lock: bool = False) -> FMRequest:
        """Đọc request; ``lock=True`` dùng trước khi đổi trạng thái để tránh race condition."""
        statement = select(FMRequest).where(FMRequest.id == request_id)
        if lock:
            statement = statement.with_for_update()
        request = await self.session.scalar(statement)
        if request is None:
            raise HTTPException(status_code=404, detail="Request not found")
        return request

    async def update_draft(self, request_id: UUID, data: RequestUpdate) -> FMRequest:
        """Chỉ requester được sửa request ở trạng thái draft hoặc returned."""
        request = await self.get_request(request_id, lock=True)
        if request.requester_id != self.actor_id:
            raise HTTPException(status_code=403, detail="Only the requester may update this request")
        if request.status not in {"draft", "returned"}:
            raise HTTPException(status_code=409, detail="Only draft or returned requests can be updated")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(request, field, value)
        self.session.add(AuditLog(entity_type="request", entity_id=request.id, action="updated", actor_id=self.actor_id, request_id=request.id))
        await self.session.flush()
        await self.session.refresh(request)
        return request

    async def submit(self, request_id: UUID) -> FMRequest:
        """Chuyển draft sang in_review và materialize workflow step thành approval step."""
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
            # Control Plane/organizational service resolve user IDs trước khi
            # publish workflow definition; client không thể chọn approver ở đây.
            approver_ids = step.conditions.get("approver_ids", [])
            if not isinstance(approver_ids, list) or not all(isinstance(item, str) and item for item in approver_ids):
                raise HTTPException(status_code=422, detail="workflow step conditions.approver_ids must be a list of user IDs")
            approval_step = ApprovalStep(
                request_id=request.id, workflow_step_id=step.id, step_order=step.step_order,
                approver_id=approver_ids[0] if len(approver_ids) == 1 else None,
                approver_role=step.approver_role, approval_mode=step.approval_mode,
                due_at=(request.submitted_at + timedelta(days=step.due_days) if step.due_days is not None else None),
            )
            self.session.add(approval_step)
            await self.session.flush()
            for approver_id in approver_ids:
                self.session.add(ApprovalAssignment(approval_step_id=approval_step.id, approver_id=approver_id))
        self.session.add(RequestStatusHistory(request_id=request.id, from_status="draft", to_status="in_review", changed_by=self.actor_id))
        self.session.add(AuditLog(entity_type="request", entity_id=request.id, action="submitted", actor_id=self.actor_id, request_id=request.id))
        self.session.add(Notification(
            request_id=request.id, recipient_id=request.requester_id, channel="in_app",
            event_code="request_submitted", payload={"request_code": request.request_code},
        ))
        await self.session.flush()
        await self.session.refresh(request)
        return request

    async def close(self, request_id: UUID) -> FMRequest:
        """Đóng request đã được approve; history/audit là immutable record."""
        request = await self.get_request(request_id, lock=True)
        if request.requester_id != self.actor_id:
            raise HTTPException(status_code=403, detail="Only the requester may close this request")
        if request.status != "approved":
            raise HTTPException(status_code=409, detail="Only approved requests can be closed")
        request.status, request.closed_at = "closed", datetime.now(UTC)
        self.session.add(RequestStatusHistory(request_id=request.id, from_status="approved", to_status="closed", changed_by=self.actor_id))
        self.session.add(AuditLog(entity_type="request", entity_id=request.id, action="closed", actor_id=self.actor_id, request_id=request.id))
        await self.session.flush()
        await self.session.refresh(request)
        return request
