from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from typing import AsyncIterator
from uuid import uuid4

from arq import create_pool
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from novel_agent.api.router import api_router
from novel_agent.core.config import Settings, get_settings
from novel_agent.core.errors import APIError
from novel_agent.health import HealthChecker
from novel_agent.worker.settings import redis_settings_from_url

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.db_engine = engine
    app.state.redis = redis
    arq_pool = None
    try:
        # The ARQ pool is what lets the API enqueue workflow runs. A queue that
        # is down must not stop the API from starting: /health and /diagnostics
        # report the degraded state instead.
        try:
            arq_pool = await create_pool(redis_settings_from_url(settings.redis_url))
        except Exception:  # noqa: BLE001
            logger.warning("ARQ pool unavailable; run dispatch is disabled", exc_info=True)
        app.state.arq = arq_pool
        yield
    finally:
        if arq_pool is not None:
            await arq_pool.aclose()
        await engine.dispose()
        await redis.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title="Novel Agent Platform API",
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.health_checker = HealthChecker(
        version=resolved_settings.app_version,
        heartbeat_key=resolved_settings.worker_heartbeat_key,
        heartbeat_ttl_seconds=resolved_settings.worker_heartbeat_ttl_seconds,
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    def error_response(request: Request, *, code: str, message: str, details) -> JSONResponse:
        request_id = getattr(request.state, "request_id", f"req_{uuid4().hex}")
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "details": details,
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        response = error_response(request, code=exc.code, message=exc.message, details=exc.details)
        response.status_code = exc.status_code
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        response = error_response(
            request,
            code="REQUEST_VALIDATION_FAILED",
            message="Request validation failed.",
            details=jsonable_encoder(exc.errors()),
        )
        response.status_code = 422
        return response

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        response = error_response(request, code="HTTP_ERROR", message=str(exc.detail), details={})
        response.status_code = exc.status_code
        return response

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API exception", exc_info=exc)
        response = error_response(
            request,
            code="INTERNAL_ERROR",
            message="An unexpected server error occurred.",
            details={},
        )
        response.status_code = 500
        return response

    async def health(request: Request) -> JSONResponse:
        status_code, payload = await request.app.state.health_checker.check(request.app)
        return JSONResponse(status_code=status_code, content=payload)

    app.add_api_route("/health", health, methods=["GET"], operation_id="health")
    # The spec names the FastAPI endpoint /health but its M0 acceptance command
    # calls /api/health through Caddy. Keep both paths stable until /api/v1 exists.
    app.add_api_route("/api/health", health, methods=["GET"], operation_id="health_compat")
    app.include_router(api_router)
    return app


app = create_app()
