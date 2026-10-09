from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from sqlalchemy import text

logger = logging.getLogger(__name__)


def heartbeat_is_fresh(raw: str | bytes | None, *, now: float, ttl_seconds: int) -> bool:
    if raw is None:
        return False
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
        timestamp = float(payload["timestamp"])
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False

    age = now - timestamp
    return 0 <= age <= ttl_seconds


def assemble_health_response(
    components: dict[str, dict[str, Any]], *, version: str
) -> tuple[int, dict[str, Any]]:
    healthy = all(component.get("status") == "ok" for component in components.values())
    payload = {
        "status": "ok" if healthy else "degraded",
        "service": "api",
        "version": version,
        "components": components,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return (200 if healthy else 503), payload


class HealthChecker:
    def __init__(self, *, version: str, heartbeat_key: str, heartbeat_ttl_seconds: int) -> None:
        self.version = version
        self.heartbeat_key = heartbeat_key
        self.heartbeat_ttl_seconds = heartbeat_ttl_seconds

    async def check(self, app: FastAPI) -> tuple[int, dict[str, Any]]:
        components: dict[str, dict[str, Any]] = {}

        engine = getattr(app.state, "db_engine", None)
        if engine is None:
            components["postgres"] = {"status": "error", "error": "not_initialized"}
        else:
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                components["postgres"] = {"status": "ok"}
            except Exception:
                logger.warning("postgres health check failed", exc_info=True)
                components["postgres"] = {"status": "error", "error": "unavailable"}

        redis = getattr(app.state, "redis", None)
        heartbeat_raw: str | None = None
        if redis is None:
            components["redis"] = {"status": "error", "error": "not_initialized"}
            components["worker"] = {"status": "error", "error": "redis_unavailable"}
        else:
            try:
                await redis.ping()
                components["redis"] = {"status": "ok"}
                heartbeat_raw = await redis.get(self.heartbeat_key)
            except Exception:
                logger.warning("redis health check failed", exc_info=True)
                components["redis"] = {"status": "error", "error": "unavailable"}
                components["worker"] = {"status": "error", "error": "redis_unavailable"}

        if "worker" not in components:
            if heartbeat_is_fresh(
                heartbeat_raw,
                now=time.time(),
                ttl_seconds=self.heartbeat_ttl_seconds,
            ):
                heartbeat_payload = json.loads(heartbeat_raw or "{}")
                components["worker"] = {
                    "status": "ok",
                    "worker_id": heartbeat_payload.get("worker_id"),
                    "last_heartbeat": heartbeat_payload.get("timestamp"),
                }
            else:
                components["worker"] = {"status": "error", "error": "heartbeat_missing_or_stale"}

        return assemble_health_response(components, version=self.version)
