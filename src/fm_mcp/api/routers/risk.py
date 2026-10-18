"""Risk register REST API."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from fm_mcp.api.dependencies import CurrentUser, get_current_user
from fm_mcp.domain.services.risk import RiskService
from fm_mcp.infrastructure.database import get_db_session
from fm_mcp.schemas.risk import (
    RiskAssessmentCreate, RiskAssessmentRead, RiskCreate, RiskHeatmapCell, RiskList, RiskRead, RiskUpdate,
)

router = APIRouter(prefix="/api/v1/risks", tags=["risk"])


def service(session: AsyncSession, user: CurrentUser) -> RiskService:
    return RiskService(session, user.id, user.roles)


@router.post("", response_model=RiskRead, status_code=status.HTTP_201_CREATED)
async def create_risk(data: RiskCreate, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    async with session.begin():
        return await service(session, user).create(data)


@router.get("", response_model=RiskList)
async def list_risks(
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), status_filter: str | None = Query(default=None, alias="status"), request_id: UUID | None = None,
    session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user),
):
    items, total = await service(session, user).list(offset, limit, status_filter, request_id)
    return RiskList(items=items, total=total, offset=offset, limit=limit)


@router.get("/heatmap", response_model=list[RiskHeatmapCell])
async def heatmap(session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    if "fm_admin" not in user.roles:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="FM admin role required")
    return [RiskHeatmapCell(likelihood=likelihood, impact=impact, count=count) for likelihood, impact, count in await service(session, user).heatmap()]


@router.patch("/{risk_id}", response_model=RiskRead)
async def update_risk(risk_id: UUID, data: RiskUpdate, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    async with session.begin():
        return await service(session, user).update(risk_id, data)


@router.post("/{risk_id}/assessments", response_model=RiskAssessmentRead, status_code=status.HTTP_201_CREATED)
async def assess_risk(risk_id: UUID, data: RiskAssessmentCreate, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    async with session.begin():
        return await service(session, user).assess(risk_id, data)


@router.get("/{risk_id}/assessments/latest", response_model=RiskAssessmentRead | None)
async def latest_assessment(risk_id: UUID, session: AsyncSession = Depends(get_db_session), user: CurrentUser = Depends(get_current_user)):
    return await service(session, user).latest_assessment(risk_id)


