from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from arq.connections import RedisSettings

from novel_agent.core.config import get_settings
from novel_agent.worker.heartbeat import on_shutdown, on_startup
from novel_agent.worker.jobs import execute_run


async def m0_infrastructure_probe(ctx: dict[str, Any]) -> None:
    """Keep ARQ's function registry valid without introducing business work."""




def redis_settings_from_url(url: str) -> RedisSettings:
    parsed = urlparse(url)
    database = int((parsed.path or "/0").lstrip("/") or "0")
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=database,
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )


class WorkerSettings:
    # `execute_run` is the M2 business job. The infrastructure probe stays
    # registered so the M0 heartbeat contract keeps working.
    functions = [execute_run, m0_infrastructure_probe]
    redis_settings = redis_settings_from_url(get_settings().redis_url)
    on_startup = on_startup
    on_shutdown = on_shutdown
    # One mutating run per project is enforced in the service layer; a single
    # worker slot keeps node execution deterministic on the dev host.
    max_jobs = 1
