"""Approval workflow service with locked, idempotent state transitions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fm_mcp.domain.models.workflow import (
    ApprovalAction,
    ApprovalAssignment,
    ApprovalStep,
    AuditLog,
    FMRequest,
    Notification,
    RequestStatusHistory,
)


class ApprovalService:
    """Apply an approval action atomically; user identity always comes from auth."""

    def __init__(self, session: AsyncSession, actor_id: str, roles: frozenset[str]) -> None:
        self.session = session
        self.actor_id = actor_id
        self.roles = roles

    async def pending(self, offset: int, limit: int) -> tuple[list[ApprovalStep], int]:
        statement = (
            select(ApprovalStep)
            .join(FMRequest)
            .options(selectinload(ApprovalStep.assignments))
            .where(ApprovalStep.status.in_(("pending", "in_progress")), FMRequest.status == "in_review")
            .order_by(ApprovalStep.due_at.nulls_last(), ApprovalStep.created_at)
        )
        candidates = list((await self.session.scalars(statement)).unique())
        eligible = [step for step in candidates if self._is_eligible(step)]
        sequential = [step for step in eligible if await self._prior_steps_complete(step)]
        return sequential[offset : offset + limit], len(sequential)

    def _is_eligible(self, step: ApprovalStep) -> bool:
        assignment_ids = {assignment.approver_id for assignment in step.assignments}
        if assignment_ids:
            return self.actor_id in assignment_ids
        return step.approver_id == self.actor_id or step.approver_role in self.roles or "fm_admin" in self.roles

    async def _prior_steps_complete(self, step: ApprovalStep) -> bool:
        prior = await self.session.scalar(
            select(ApprovalStep.id).where(
                ApprovalStep.request_id == step.request_id,
                ApprovalStep.step_order < step.step_order,
                ApprovalStep.status.not_in(("approved", "skipped")),
            ).limit(1)
        )
        return prior is None

    async def act(
        self, step_id: UUID, action_name: str, comment: str | None, idempotency_key: str | None
    ) -> tuple[ApprovalStep, FMRequest, ApprovalAction]:
        if idempotency_key:
            prior_action = await self.session.scalar(
                select(ApprovalAction).where(ApprovalAction.idempotency_key == idempotency_key)
            )
            if prior_action:
                step = await self.session.scalar(
                    select(ApprovalStep).options(selectinload(ApprovalStep.assignments)).where(ApprovalStep.id == prior_action.approval_step_id)
                )
                if step is None:
                    raise HTTPException(status_code=409, detail="Idempotency record is invalid")
                request = await self.session.get(FMRequest, step.request_id)
                if request is None:
                    raise HTTPException(status_code=409, detail="Request was removed")
                return step, request, prior_action

        step = await self.session.scalar(
            select(ApprovalStep)
            .options(selectinload(ApprovalStep.assignments))
            .where(ApprovalStep.id == step_id)
            .with_for_update()
        )
        if step is None:
            raise HTTPException(status_code=404, detail="Approval step not found")
        request = await self.session.scalar(select(FMRequest).where(FMRequest.id == step.request_id).with_for_update())
        if request is None:
            raise HTTPException(status_code=404, detail="Request not found")
        if request.status != "in_review" or step.status not in {"pending", "in_progress"}:
            raise HTTPException(status_code=409, detail="Approval step is no longer actionable")
        if not await self._prior_steps_complete(step):
            raise HTTPException(status_code=409, detail="Previous approval step must be completed first")
        if not self._is_eligible(step):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not an eligible approver")

        assignment = next((item for item in step.assignments if item.approver_id == self.actor_id), None)
        if assignment and assignment.status != "pending":
            raise HTTPException(status_code=409, detail="You have already acted on this step")
        now = datetime.now(UTC)
        if assignment:
            assignment.status, assignment.acted_at = self._assignment_status(action_name), now
        elif step.approver_id is None:
            # Role-based fallback when Control Plane has not supplied person-level assignments.
            step.approver_id = self.actor_id

        action = ApprovalAction(
            approval_step_id=step.id,
            approval_assignment_id=assignment.id if assignment else None,
            actor_id=self.actor_id,
            action=action_name,
            comment=comment,
            idempotency_key=idempotency_key,
        )
        self.session.add(action)
        if action_name == "approve":
            await self._approve(step, request, now)
        else:
            await self._terminate(step, request, action_name, comment, now)
        self.session.add(AuditLog(
            entity_type="approval_step", entity_id=step.id, action=action_name,
            actor_id=self.actor_id, request_id=request.id,
        ))
        await self.session.flush()
        await self.session.refresh(request)
        await self.session.refresh(step, attribute_names=["assignments"])
        return step, request, action

    @staticmethod
    def _assignment_status(action_name: str) -> str:
        return {"approve": "approved", "reject": "rejected", "return": "returned"}[action_name]

    async def _approve(self, step: ApprovalStep, request: FMRequest, now: datetime) -> None:
        if step.assignments:
            approved = all(item.status == "approved" for item in step.assignments)
            if step.approval_mode == "any" and any(item.status == "approved" for item in step.assignments):
                for item in step.assignments:
                    if item.status == "pending":
                        item.status = "skipped"
                approved = True
            if not approved:
                step.status = "in_progress"
                step.started_at = step.started_at or now
                return
        step.status, step.started_at, step.completed_at = "approved", step.started_at or now, now
        has_next = await self.session.scalar(
            select(ApprovalStep.id).where(
                ApprovalStep.request_id == request.id,
                ApprovalStep.step_order > step.step_order,
                ApprovalStep.status.in_(("pending", "in_progress")),
            ).limit(1)
        )
        if has_next is None:
            request.status = "approved"
            self.session.add(RequestStatusHistory(
                request_id=request.id, from_status="in_review", to_status="approved", changed_by=self.actor_id
            ))
            self.session.add(Notification(
                request_id=request.id, recipient_id=request.requester_id, channel="in_app",
                event_code="request_approved", payload={"request_code": request.request_code},
            ))

    async def _terminate(
        self, step: ApprovalStep, request: FMRequest, action_name: str, comment: str | None, now: datetime
    ) -> None:
        target = "rejected" if action_name == "reject" else "returned"
        step.status, step.started_at, step.completed_at = target, step.started_at or now, now
        for item in step.assignments:
            if item.status == "pending":
                item.status, item.acted_at = target, now
        remaining = await self.session.scalars(
            select(ApprovalStep).where(
                ApprovalStep.request_id == request.id,
                ApprovalStep.step_order > step.step_order,
                ApprovalStep.status.in_(("pending", "in_progress")),
            )
        )
        for item in remaining:
            item.status = "skipped"
        request.status = target
        self.session.add(RequestStatusHistory(
            request_id=request.id, from_status="in_review", to_status=target,
            changed_by=self.actor_id, comment=comment,
        ))
        self.session.add(Notification(
            request_id=request.id, recipient_id=request.requester_id, channel="in_app",
            event_code=f"request_{target}", payload={"request_code": request.request_code, "comment": comment},
        ))

    async def history(self, step_id: UUID) -> list[ApprovalAction]:
        step = await self.session.scalar(
            select(ApprovalStep).options(selectinload(ApprovalStep.assignments)).where(ApprovalStep.id == step_id)
        )
        if step is None:
            raise HTTPException(status_code=404, detail="Approval step not found")
        if not self._is_eligible(step) and "fm_admin" not in self.roles:
            raise HTTPException(status_code=403, detail="Not allowed")
        result = await self.session.scalars(
            select(ApprovalAction).where(ApprovalAction.approval_step_id == step_id).order_by(ApprovalAction.acted_at)
        )
        return list(result)
