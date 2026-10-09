from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_agent.core.config import get_settings
from novel_agent.presets.service import ensure_builtin_presets


async def bootstrap() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            await ensure_builtin_presets(session, settings)
            await session.commit()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(bootstrap())
