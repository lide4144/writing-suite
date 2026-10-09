"""Diagnostics and debug read endpoints (spec §10.2, §11)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_agent.api.runs import define_run_read
from novel_agent.api.schemas import (
    ArtifactRead,
    DebugTraceResponse,
    DiagnosticsComponent,
    DiagnosticsResponse,
    LlmCallRead,
    RunEventRead,
    RunNodeRead,
)
from novel_agent.artifacts.registry import ArtifactRegistry, artifact_read
from novel_agent.core.errors import APIError
from novel_agent.db.models import Artifact, ContextItem, Event, LlmCall, Run, RunNode
from novel_agent.db.session import get_db
from novel_agent.tracing.events import event_payload

router = APIRouter(tags=["diagnostics"])


async def _run_or_404(session: AsyncSession, run_id: UUID) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        raise APIError("RUN_NOT_FOUND", "The requested run does not exist.", status_code=404)
    return run


@router.get("/diagnostics", response_model=DiagnosticsResponse, operation_id="get_diagnostics")
async def get_diagnostics(request: Request, session: AsyncSession = Depends(get_db)) -> DiagnosticsResponse:
    """Explain dependency failures; never expose secrets (spec §10.2, §10.3)."""

    settings = request.app.state.settings
    components: dict[str, DiagnosticsComponent] = {}

    from sqlalchemy import text as sql_text

    try:
        await session.execute(sql_text("SELECT 1"))
        components["postgres"] = DiagnosticsComponent(status="ok")
    except Exception as exc:  # noqa: BLE001
        components["postgres"] = DiagnosticsComponent(status="error", error="unavailable", details={"type": type(exc).__name__})

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        components["redis"] = DiagnosticsComponent(status="error", error="not_initialized")
        components["worker"] = DiagnosticsComponent(status="error", error="redis_unavailable")
    else:
        try:
            await redis.ping()
            components["redis"] = DiagnosticsComponent(status="ok")
            raw = await redis.get(settings.worker_heartbeat_key)
            if raw is None:
                components["worker"] = DiagnosticsComponent(status="error", error="heartbeat_missing")
            else:
                payload = json.loads(raw)
                age = time.time() - float(payload.get("timestamp", 0))
                if age <= settings.worker_heartbeat_ttl_seconds:
                    components["worker"] = DiagnosticsComponent(
                        status="ok", details={"worker_id": payload.get("worker_id"), "age_seconds": round(age, 2)}
                    )
                else:
                    components["worker"] = DiagnosticsComponent(
                        status="error", error="heartbeat_stale", details={"age_seconds": round(age, 2)}
                    )
        except Exception:  # noqa: BLE001
            components["redis"] = DiagnosticsComponent(status="error", error="unavailable")
            components["worker"] = DiagnosticsComponent(status="error", error="redis_unavailable")

    projects_root = Path(settings.projects_root).expanduser()
    if projects_root.is_dir():
        writable = _is_writable(projects_root)
        components["projects_root"] = DiagnosticsComponent(
            status="ok" if writable else "error",
            error=None if writable else "not_writable",
            details={"path": str(projects_root)},
        )
    else:
        components["projects_root"] = DiagnosticsComponent(
            status="error", error="missing", details={"path": str(projects_root)}
        )

    schemas_root = Path(settings.artifact_schemas_root).expanduser()
    schema_files = sorted(schemas_root.glob("*.json")) if schemas_root.is_dir() else []
    components["artifact_schemas"] = DiagnosticsComponent(
        status="ok" if schema_files else "error",
        error=None if schema_files else "no_schemas_found",
        details={"path": str(schemas_root), "count": len(schema_files)},
    )

    git_available = _git_available()
    components["git"] = DiagnosticsComponent(status="ok" if git_available else "error", error=None if git_available else "git_missing")

    try:
        from sqlalchemy import func

        from novel_agent.db.models import ModelEndpoint

        enabled = (
            await session.execute(
                select(func.count()).select_from(ModelEndpoint).where(ModelEndpoint.enabled.is_(True))
            )
        ).scalar_one()
        components["model_endpoints"] = DiagnosticsComponent(
            status="ok",
            details={"enabled": int(enabled), "note": "no enabled endpoint is a warning, not a failure"},
        )
    except Exception:  # noqa: BLE001
        components["model_endpoints"] = DiagnosticsComponent(status="error", error="query_failed")

    healthy = all(component.status == "ok" for component in components.values())
    return DiagnosticsResponse(
        status="ok" if healthy else "degraded",
        version=settings.app_version,
        components=components,
        timestamp=datetime.now(timezone.utc),
    )


def _is_writable(path: Path) -> bool:
    import os

    return os.access(path, os.W_OK)


def _git_available() -> bool:
    import shutil

    return shutil.which("git") is not None


async def _nodes(session: AsyncSession, run_id: UUID) -> list[RunNode]:
    statement = select(RunNode).where(RunNode.run_id == run_id).order_by(RunNode.started_at.asc().nulls_last())
    return list((await session.execute(statement)).scalars().all())


async def _events(session: AsyncSession, run_id: UUID) -> list[Event]:
    statement = select(Event).where(Event.run_id == run_id).order_by(Event.sequence.asc())
    return list((await session.execute(statement)).scalars().all())


async def _llm_calls(session: AsyncSession, run_id: UUID) -> list[LlmCall]:
    statement = select(LlmCall).where(LlmCall.run_id == run_id).order_by(LlmCall.created_at.asc())
    return list((await session.execute(statement)).scalars().all())


async def _artifacts(session: AsyncSession, run_id: UUID) -> list[Artifact]:
    statement = select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at.asc())
    return list((await session.execute(statement)).scalars().all())


@router.get("/debug/runs/{run_id}/events", response_model=list[RunEventRead], operation_id="debug_run_events")
async def debug_run_events(run_id: UUID, session: AsyncSession = Depends(get_db)) -> list[dict]:
    await _run_or_404(session, run_id)
    return [event_payload(event) for event in await _events(session, run_id)]


@router.get("/debug/runs/{run_id}/llm-calls", response_model=list[LlmCallRead], operation_id="debug_run_llm_calls")
async def debug_run_llm_calls(run_id: UUID, session: AsyncSession = Depends(get_db)) -> list[LlmCall]:
    await _run_or_404(session, run_id)
    return await _llm_calls(session, run_id)


@router.get("/debug/runs/{run_id}/artifacts", response_model=list[ArtifactRead], operation_id="debug_run_artifacts")
async def debug_run_artifacts(run_id: UUID, session: AsyncSession = Depends(get_db)) -> list[dict]:
    await _run_or_404(session, run_id)
    return [artifact_read(artifact) for artifact in await _artifacts(session, run_id)]


@router.get("/debug/runs/{run_id}/context", operation_id="debug_run_context")
async def debug_run_context(run_id: UUID, session: AsyncSession = Depends(get_db)) -> list[dict]:
    await _run_or_404(session, run_id)
    calls = await _llm_calls(session, run_id)
    call_ids = [call.id for call in calls]
    if not call_ids:
        return []
    from novel_agent.db.models import LlmCallContext

    rows = (
        await session.execute(
            select(LlmCallContext, ContextItem)
            .join(ContextItem, ContextItem.id == LlmCallContext.context_item_id)
            .where(LlmCallContext.llm_call_id.in_(call_ids))
            .order_by(LlmCallContext.rank.asc())
        )
    ).all()
    return [
        {
            "llm_call_id": str(link.llm_call_id),
            "context_item_id": str(item.id),
            "kind": item.kind,
            "source_ref": item.source_ref,
            "rank": link.rank,
            "score": link.score,
            "reason": link.reason,
            "text_preview": item.text[:280],
        }
        for link, item in rows
    ]


@router.get("/debug/runs/{run_id}/errors", operation_id="debug_run_errors")
async def debug_run_errors(run_id: UUID, session: AsyncSession = Depends(get_db)) -> list[dict]:
    run = await _run_or_404(session, run_id)
    errors: list[dict] = []
    if run.error_code:
        errors.append(
            {
                "scope": "run",
                "code": run.error_code,
                "message": run.error_message,
                "node_key": run.current_node,
                "run_id": str(run.id),
            }
        )
    for node in await _nodes(session, run_id):
        if node.status == "failed":
            errors.append(
                {
                    "scope": "node",
                    "code": node.error_code,
                    "message": node.error_message,
                    "node_key": node.node_key,
                    "attempt": node.attempt,
                    "run_id": str(run.id),
                }
            )
    for call in await _llm_calls(session, run_id):
        if call.status == "failed":
            errors.append(
                {
                    "scope": "llm_call",
                    "code": "LLM_CALL_FAILED",
                    "message": call.error,
                    "agent_key": call.agent_key,
                    "llm_call_id": str(call.id),
                    "run_id": str(run.id),
                }
            )
    return errors


@router.get("/debug/runs/{run_id}/trace", response_model=DebugTraceResponse, operation_id="debug_run_trace")
async def debug_run_trace(run_id: UUID, request: Request, session: AsyncSession = Depends(get_db)) -> DebugTraceResponse:
    run = await _run_or_404(session, run_id)
    registry = ArtifactRegistry(session, request.app.state.settings)
    artifacts = await _artifacts(session, run_id)
    return DebugTraceResponse(
        run=define_run_read(run),
        nodes=[RunNodeRead.model_validate(node) for node in await _nodes(session, run_id)],
        artifacts=[ArtifactRead(**artifact_read(artifact)) for artifact in artifacts],
        events=[RunEventRead(**event_payload(event)) for event in await _events(session, run_id)],
        llm_calls=[LlmCallRead.model_validate(call) for call in await _llm_calls(session, run_id)],
        errors=await debug_run_errors(run_id, session),
    )


__all__ = ["router"]
