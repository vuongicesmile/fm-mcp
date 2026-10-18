"""Async SQLAlchemy infrastructure for the Workflow Automation API."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from fm_mcp.api.settings import api_settings


class Base(DeclarativeBase):
    """Base class registered as Alembic target metadata."""


engine = create_async_engine(api_settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Provide one transaction-capable database session per API request."""
    async with SessionLocal() as session:
        yield session
