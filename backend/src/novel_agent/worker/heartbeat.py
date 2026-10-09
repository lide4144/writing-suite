from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from redis.asyncio import Redis

from novel_agent.core.config import Settings, get_settings


def heartbeat_payload(settings: Settings) -> dict[str, Any]:
    return {
        "worker_id": settings.worker_id,
        "timestamp": time.time(),
        "app_version": settings.app_version,
    }


async def write_heartbeat(redis: Redis, settings: Settings) -> None:
    await redis.set(
        settings.worker_heartbeat_key,
        json.dumps(heartbeat_payload(settings), separators=(",", ":")),
        ex=settings.worker_heartbeat_ttl_seconds,
    )


async def heartbeat_loop(redis: Redis, settings: Settings) -> None:
    while True:
        await write_heartbeat(redis, settings)
        await asyncio.sleep(settings.worker_heartbeat_interval_seconds)


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await write_heartbeat(redis, settings)
    ctx["heartbeat_redis"] = redis
    ctx["heartbeat_task"] = asyncio.create_task(heartbeat_loop(redis, settings))


async def on_shutdown(ctx: dict[str, Any]) -> None:
    task = ctx.get("heartbeat_task")
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    redis: Redis | None = ctx.get("heartbeat_redis")
    if redis is not None:
        settings = get_settings()
        await redis.delete(settings.worker_heartbeat_key)
        await redis.aclose()
