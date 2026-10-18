"""Approval endpoints. Approval identity is derived only from authentication."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from fm_mcp.api.dependencies import CurrentUser, get_current_user
from fm_mcp.domain.services.approval import ApprovalService
from fm_mcp.infrastructure.database import get_db_session
from fm_mcp.schemas.approval import ApprovalActionCreate, ApprovalActionResult, ApprovalList, ApprovalStepRead

router = APIRouter(prefix="/api/v1/approvals", tags=["approval"])


@router.get("/pending", response_model=ApprovalList)
async def pending_approvals(
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user),
):
    items, total = await ApprovalService(session, user.id, user.roles).pending(offset, limit)
    return ApprovalList(items=[ApprovalStepRead.model_validate(item) for item in items], total=total, offset=offset, limit=limit)


async def _act(
    step_id: UUID, action_name: str, payload: ApprovalActionCreate, idempotency_key: str | None,
    session: AsyncSession, user: CurrentUser,
) -> ApprovalActionResult:
    async with session.begin():
        step, request, action = await ApprovalService(session, user.id, user.roles).act(
            step_id, action_name, payload.comment, idempotency_key
        )
        return ApprovalActionResult(
            approval_step=ApprovalStepRead.model_validate(step), request_status=request.status, action=action
        )


@router.post("/{step_id}/approve", response_model=ApprovalActionResult)
async def approve(
    step_id: UUID, payload: ApprovalActionCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user),
):
    return await _act(step_id, "approve", payload, idempotency_key, session, user)


@router.post("/{step_id}/reject", response_model=ApprovalActionResult)
async def reject(
    step_id: UUID, payload: ApprovalActionCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user),
):
    return await _act(step_id, "reject", payload, idempotency_key, session, user)


@router.post("/{step_id}/return", response_model=ApprovalActionResult)
async def return_for_revision(
    step_id: UUID, payload: ApprovalActionCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user),
):
    return await _act(step_id, "return", payload, idempotency_key, session, user)


@router.get("/{step_id}/history")
async def approval_history(
    step_id: UUID, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user),
):
    return await ApprovalService(session, user.id, user.roles).history(step_id)
