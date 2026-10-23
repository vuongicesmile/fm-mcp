"""Continuously deliver due email notifications from the FM outbox."""

import asyncio

from fm_mcp.domain.services.delivery import NotificationDeliveryWorker
from fm_mcp.infrastructure.database import SessionLocal


async def main() -> None:
    worker = NotificationDeliveryWorker(SessionLocal)
    while True:
        await worker.run_once()
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
