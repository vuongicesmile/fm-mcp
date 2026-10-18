"""Risk register service. The 1–5 product score is a configurable deployment default."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fm_mcp.domain.models.workflow import AuditLog, FMRequest, Risk, RiskAssessment
from fm_mcp.schemas.risk import RiskAssessmentCreate, RiskCreate, RiskUpdate


class RiskService:
    """Risk Register rules; owner/creator/admin mới có quyền thay đổi risk."""
    def __init__(self, session: AsyncSession, actor_id: str, roles: frozenset[str]) -> None:
        self.session, self.actor_id, self.roles = session, actor_id, roles

    def _can_manage(self, risk: Risk) -> bool:
        return "fm_admin" in self.roles or risk.created_by == self.actor_id or risk.owner_id == self.actor_id

    async def create(self, data: RiskCreate) -> Risk:
        """Tạo risk code, validate request link (nếu có) và ghi audit."""
        if data.request_id and not await self.session.get(FMRequest, data.request_id):
            raise HTTPException(status_code=404, detail="Request not found")
        risk = Risk(
            risk_code=f"RSK-{uuid4().hex[:12].upper()}", created_by=self.actor_id,
            **data.model_dump(),
        )
        self.session.add(risk)
        await self.session.flush()
        self.session.add(AuditLog(entity_type="risk", entity_id=risk.id, action="created", actor_id=self.actor_id, request_id=risk.request_id))
        await self.session.flush()
        await self.session.refresh(risk)
        return risk

    async def get(self, risk_id: UUID) -> Risk:
        risk = await self.session.get(Risk, risk_id)
        if risk is None:
            raise HTTPException(status_code=404, detail="Risk not found")
        if not self._can_manage(risk):
            raise HTTPException(status_code=403, detail="Not allowed")
        return risk

    async def update(self, risk_id: UUID, data: RiskUpdate) -> Risk:
        """Lock risk trước khi update để audit phản ánh đúng version thay đổi."""
        risk = await self.session.scalar(select(Risk).where(Risk.id == risk_id).with_for_update())
        if risk is None:
            raise HTTPException(status_code=404, detail="Risk not found")
        if not self._can_manage(risk):
            raise HTTPException(status_code=403, detail="Not allowed")
        before = {field: getattr(risk, field) for field in data.model_fields_set}
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(risk, field, value)
        self.session.add(AuditLog(
            entity_type="risk", entity_id=risk.id, action="updated", actor_id=self.actor_id,
            request_id=risk.request_id, before_data={key: str(value) if value is not None else None for key, value in before.items()},
        ))
        await self.session.flush()
        await self.session.refresh(risk)
        return risk

    async def list(self, offset: int, limit: int, status_filter: str | None, request_id: UUID | None) -> tuple[list[Risk], int]:
        filters = []
        if status_filter:
            filters.append(Risk.status == status_filter)
        if request_id:
            filters.append(Risk.request_id == request_id)
        if "fm_admin" not in self.roles:
            filters.append((Risk.created_by == self.actor_id) | (Risk.owner_id == self.actor_id))
        statement = select(Risk).where(*filters).order_by(Risk.updated_at.desc())
        total = await self.session.scalar(select(func.count()).select_from(Risk).where(*filters))
        items = list((await self.session.scalars(statement.offset(offset).limit(limit))).all())
        return items, total or 0

    async def assess(self, risk_id: UUID, data: RiskAssessmentCreate) -> RiskAssessment:
        """Lưu assessment; score mặc định là likelihood × impact theo schema 1–5."""
        risk = await self.get(risk_id)
        score = data.risk_score if data.risk_score is not None else data.likelihood * data.impact
        assessment = RiskAssessment(
            risk_id=risk.id, likelihood=data.likelihood, impact=data.impact, risk_score=score,
            assessment_type=data.assessment_type, notes=data.notes, assessed_by=self.actor_id,
        )
        self.session.add(assessment)
        self.session.add(AuditLog(entity_type="risk", entity_id=risk.id, action="assessed", actor_id=self.actor_id, request_id=risk.request_id))
        await self.session.flush()
        await self.session.refresh(assessment)
        return assessment

    async def latest_assessment(self, risk_id: UUID) -> RiskAssessment | None:
        await self.get(risk_id)
        return await self.session.scalar(
            select(RiskAssessment).where(RiskAssessment.risk_id == risk_id).order_by(RiskAssessment.assessed_at.desc()).limit(1)
        )

    async def heatmap(self) -> list[tuple[int, int, int]]:
        """Đếm assessment mới nhất của mỗi risk theo ô likelihood/impact."""
        # DISTINCT ON is PostgreSQL-specific and selects the newest assessment per risk.
        latest = (
            select(RiskAssessment.risk_id, RiskAssessment.likelihood, RiskAssessment.impact)
            .distinct(RiskAssessment.risk_id)
            .order_by(RiskAssessment.risk_id, RiskAssessment.assessed_at.desc())
            .subquery()
        )
        result = await self.session.execute(
            select(latest.c.likelihood, latest.c.impact, func.count())
            .group_by(latest.c.likelihood, latest.c.impact)
            .order_by(latest.c.likelihood, latest.c.impact)
        )
        return [(int(likelihood), int(impact), int(count)) for likelihood, impact, count in result.all()]
