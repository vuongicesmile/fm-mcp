"""Workflow definition and request REST endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fm_mcp.api.dependencies import CurrentUser, get_current_user, require_role
from fm_mcp.domain.models.workflow import FMRequest, RequestStatusHistory, WorkflowDefinition, WorkflowStep
from fm_mcp.domain.services.workflow import WorkflowService
from fm_mcp.domain.services.notification import NotificationService
from fm_mcp.infrastructure.database import get_db_session
from fm_mcp.schemas.workflow import (
    RequestCreate, RequestList, RequestRead, RequestStatusHistoryRead, RequestUpdate, WorkflowDefinitionCreate, WorkflowDefinitionRead,
)

router = APIRouter(prefix="/api/v1", tags=["workflow"])


@router.get("/workflows", response_model=list[WorkflowDefinitionRead])
async def list_workflows(session: AsyncSession = Depends(get_db_session), _: CurrentUser = Depends(get_current_user)):
    result = await session.scalars(select(WorkflowDefinition).where(WorkflowDefinition.is_active.is_(True)).options(selectinload(WorkflowDefinition.steps)))
    return list(result.unique())


@router.post("/workflows", response_model=WorkflowDefinitionRead, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    data: WorkflowDefinitionCreate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_role("fm_admin")),
):
    """Tạo workflow definition cùng các bước duyệt trong một transaction."""
    async with session.begin():
        exists = await session.scalar(
            select(WorkflowDefinition.id).where(
                WorkflowDefinition.code == data.code,
                WorkflowDefinition.version == data.version,
            )
        )
        if exists is not None:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail="Workflow definition version already exists")
        workflow = WorkflowDefinition(
            code=data.code,
            name=data.name,
            description=data.description,
            version=data.version,
            is_active=data.is_active,
        )
        session.add(workflow)
        await session.flush()
        for step in data.steps:
            session.add(WorkflowStep(workflow_definition_id=workflow.id, **step.model_dump()))
        await session.flush()
        result = await session.scalar(
            select(WorkflowDefinition)
            .where(WorkflowDefinition.id == workflow.id)
            .options(selectinload(WorkflowDefinition.steps))
        )
        assert result is not None
        return result


@router.post("/requests", response_model=RequestRead, status_code=status.HTTP_201_CREATED)
async def create_request(data: RequestCreate, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    async with session.begin():
        return await WorkflowService(session, user.id).create_request(data)


@router.get("/requests", response_model=RequestList)
async def list_requests(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    statement = select(FMRequest).where(FMRequest.requester_id == user.id).order_by(FMRequest.created_at.desc()).offset(offset).limit(limit)
    items = list((await session.scalars(statement)).all())
    total = await session.scalar(select(func.count()).select_from(FMRequest).where(FMRequest.requester_id == user.id))
    return RequestList(items=items, total=total or 0, offset=offset, limit=limit)


@router.get("/requests/overdue", response_model=RequestList)
async def overdue_requests(
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user),
):
    items, total = await NotificationService(session, user.id, user.roles).overdue_requests(offset, limit)
    return RequestList(items=items, total=total, offset=offset, limit=limit)


@router.get("/requests/{request_id}", response_model=RequestRead)
async def get_request(request_id: UUID, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    request = await WorkflowService(session, user.id).get_request(request_id)
    if request.requester_id != user.id and "fm_admin" not in user.roles:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not allowed")
    return request


@router.patch("/requests/{request_id}", response_model=RequestRead)
async def update_request(request_id: UUID, data: RequestUpdate, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    async with session.begin():
        return await WorkflowService(session, user.id).update_draft(request_id, data)


@router.post("/requests/{request_id}/submit", response_model=RequestRead)
async def submit_request(request_id: UUID, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    async with session.begin():
        return await WorkflowService(session, user.id).submit(request_id)


@router.post("/requests/{request_id}/close", response_model=RequestRead)
async def close_request(request_id: UUID, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    async with session.begin():
        return await WorkflowService(session, user.id).close(request_id)


@router.get("/requests/{request_id}/history", response_model=list[RequestStatusHistoryRead])
async def request_history(request_id: UUID, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    request = await WorkflowService(session, user.id).get_request(request_id)
    if request.requester_id != user.id and "fm_admin" not in user.roles:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not allowed")
    result = await session.scalars(select(RequestStatusHistory).where(RequestStatusHistory.request_id == request_id).order_by(RequestStatusHistory.changed_at))
    return list(result)
