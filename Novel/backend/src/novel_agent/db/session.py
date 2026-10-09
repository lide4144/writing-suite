from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from novel_agent.core.errors import APIError


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session created by the application lifespan."""

    engine = getattr(request.app.state, "db_engine", None)
    if engine is None:
        raise APIError("DATABASE_NOT_INITIALIZED", "Database is not initialized.", status_code=503)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
