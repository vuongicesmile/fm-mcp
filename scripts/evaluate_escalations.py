"""Run one idempotent escalation scan from a trusted scheduler worker."""

import asyncio

from fm_mcp.domain.services.notification import NotificationService
from fm_mcp.infrastructure.database import SessionLocal


async def main() -> None:
    async with SessionLocal() as session:
        async with session.begin():
            count = await NotificationService(
                session, actor_id="scheduler", roles=frozenset({"fm_admin"})
            ).evaluate_escalations()
    print(f"Created {count} escalation reminder(s)")


if __name__ == "__main__":
    asyncio.run(main())
