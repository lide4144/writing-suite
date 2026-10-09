"""ARQ jobs executed by the worker (spec §3.2)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from novel_agent.core.config import get_settings
from novel_agent.db.models import Run
from novel_agent.providers.factory import build_provider
from novel_agent.workflows.runner import RunExecutor, RunState  # noqa: F401  (RunState re-exported for tests)

logger = logging.getLogger(__name__)


async def execute_run(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Execute one workflow run. Registered as the `execute_run` ARQ job."""

    # Settings and engine come from the worker context when present so embedded
    # runs (tests, in-process execution) share the caller's configuration.
    settings = ctx.get("settings") or get_settings()
    engine = ctx.get("db_engine")
    owns_engine = engine is None
    if engine is None:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        ctx["db_engine"] = engine

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            run = await session.get(Run, UUID(str(run_id)))
            if run is None:
                logger.warning("execute_run: run %s no longer exists", run_id)
                return {"run_id": str(run_id), "status": "missing"}
            if run.status == "cancelled":
                return {"run_id": str(run.id), "status": run.status}
            provider = await build_provider(session, settings, run)
            executor = RunExecutor(session, settings, provider)
            executed = await executor.execute(run.id)
            return {"run_id": str(executed.id), "status": executed.status, "current_node": executed.current_node}
    finally:
        if owns_engine:
            await engine.dispose()
