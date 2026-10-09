from __future__ import annotations

import asyncio
import time

from redis.asyncio import Redis

from novel_agent.core.config import get_settings
from novel_agent.health import heartbeat_is_fresh


async def check() -> int:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = await redis.get(settings.worker_heartbeat_key)
        return int(
            heartbeat_is_fresh(
                raw,
                now=time.time(),
                ttl_seconds=settings.worker_heartbeat_ttl_seconds,
            )
        )
    finally:
        await redis.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check()))
