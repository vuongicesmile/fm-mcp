"""Database-backed email outbox worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from fm_mcp.api.settings import api_settings
from fm_mcp.domain.models.workflow import Notification
from fm_mcp.infrastructure.email import SMTPEmailSender, render_template


@dataclass(frozen=True)
class EmailDelivery:
    notification_id: UUID
    recipient: str
    subject: str
    body: str


class NotificationDeliveryWorker:
    """Claims one email at a time with SKIP LOCKED, then sends outside the DB transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], sender: SMTPEmailSender | None = None) -> None:
        self.sessions = sessions
        self.sender = sender or SMTPEmailSender()

    async def run_once(self, limit: int = 100) -> int:
        sent = 0
        for _ in range(limit):
            delivery = await self._claim()
            if delivery is None:
                break
            try:
                await self.sender.send(delivery.recipient, delivery.subject, delivery.body)
            except Exception as error:  # SMTP failures are persisted; secrets are never logged.
                await self._finalize(delivery.notification_id, sent=False, error=str(error))
            else:
                await self._finalize(delivery.notification_id, sent=True)
                sent += 1
        return sent

    async def _claim(self) -> EmailDelivery | None:
        async with self.sessions() as session:
            async with session.begin():
                notification = await session.scalar(
                    select(Notification)
                    .options(selectinload(Notification.template))
                    .where(
                        Notification.channel == "email",
                        Notification.status.in_(("pending", "failed")),
                        Notification.scheduled_at <= datetime.now(UTC),
                        Notification.attempt_count < api_settings.smtp_max_attempts,
                    )
                    .order_by(Notification.scheduled_at, Notification.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if notification is None:
                    return None
                notification.status = "sending"
                notification.attempt_count += 1
                if not notification.recipient_address:
                    raise ValueError("Email notification has no recipient_address")
                payload = notification.payload
                subject_template = notification.template.subject_template if notification.template else None
                body_template = notification.template.body_template if notification.template else None
                subject = render_template(subject_template or str(payload.get("subject", f"FM notification: {notification.event_code}")), payload)
                body = render_template(body_template or str(payload.get("body", "")), payload)
                return EmailDelivery(notification.id, notification.recipient_address, subject, body)

    async def _finalize(self, notification_id: UUID, *, sent: bool, error: str | None = None) -> None:
        async with self.sessions() as session:
            async with session.begin():
                notification = await session.scalar(
                    select(Notification).where(Notification.id == notification_id).with_for_update()
                )
                if notification is None:
                    return
                notification.status = "sent" if sent else "failed"
                notification.sent_at = datetime.now(UTC) if sent else None
                notification.last_error = None if sent else (error or "SMTP delivery failed")[:4000]
                if not sent:
                    notification.scheduled_at = datetime.now(UTC) + timedelta(seconds=api_settings.smtp_retry_delay_seconds)
