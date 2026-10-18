"""Notification read APIs and administrator configuration endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from fm_mcp.api.dependencies import CurrentUser, get_current_user
from fm_mcp.domain.services.notification import NotificationService
from fm_mcp.infrastructure.database import get_db_session
from fm_mcp.schemas.notification import (
    EscalationRuleCreate, EscalationRuleRead, EscalationRuleUpdate, NotificationCreate, NotificationList,
    NotificationRead, NotificationTemplateCreate, NotificationTemplateRead, NotificationTemplateUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["notification"])


def service(session: AsyncSession, user: CurrentUser) -> NotificationService:
    return NotificationService(session, user.id, user.roles)


@router.get("/notifications", response_model=NotificationList)
async def list_notifications(
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), request_id: UUID | None = None,
    session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user),
):
    items, total = await service(session, user).list_notifications(offset, limit, request_id)
    return NotificationList(items=items, total=total, offset=offset, limit=limit)


@router.post("/notifications", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
async def queue_notification(data: NotificationCreate, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    async with session.begin():
        return await service(session, user).queue(data)


@router.post("/notification-templates", response_model=NotificationTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(data: NotificationTemplateCreate, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    async with session.begin():
        return await service(session, user).create_template(data)


@router.patch("/notification-templates/{template_id}", response_model=NotificationTemplateRead)
async def update_template(template_id: UUID, data: NotificationTemplateUpdate, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    async with session.begin():
        return await service(session, user).update_template(template_id, data)


@router.post("/escalation-rules", response_model=EscalationRuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(data: EscalationRuleCreate, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    async with session.begin():
        return await service(session, user).create_rule(data)


@router.patch("/escalation-rules/{rule_id}", response_model=EscalationRuleRead)
async def update_rule(rule_id: UUID, data: EscalationRuleUpdate, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    async with session.begin():
        return await service(session, user).update_rule(rule_id, data)
