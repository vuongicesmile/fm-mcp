"""Send due email notifications through the configured SMTP relay."""

import asyncio

from fm_mcp.domain.services.delivery import NotificationDeliveryWorker
from fm_mcp.infrastructure.database import SessionLocal


async def main() -> None:
    sent = await NotificationDeliveryWorker(SessionLocal).run_once()
    print(f"Sent {sent} email notification(s)")


if __name__ == "__main__":
    asyncio.run(main())
