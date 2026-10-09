"""Run endpoints: create, read, cancel, retry, events and SSE (spec §10.1, §11)."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from novel_agent.api.idempotency import existing_action, idempotency_key, record_action
from novel_agent.api.schemas import (
    QualityGateRead,
    RunCreateRequest,
    RunCreateResponse,
    RunEventsResponse,
    RunLinks,
    RunNodeRead,
    RunRead,
)
from novel_agent.core.errors import APIError
from novel_agent.db.models import Project, Run, RunNode
from novel_agent.db.session import get_db
from novel_agent.domain.states import is_terminal_run_status
from novel_agent.providers.factory import RUN_MODES, build_provider  # noqa: F401  (RUN_MODES re-exported)
from novel_agent.tracing.events import event_payload, to_sse
from novel_agent.workflows.definitions import get_workflow
from novel_agent.workflows.service import RunService

router = APIRouter(tags=["runs"])

_TERMINAL = {"succeeded", "failed", "cancelled"}


async def _project_or_404(session: AsyncSession, project_id: UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise APIError("PROJECT_NOT_FOUND", "The requested project does not exist.", status_code=404)
    return project


async def _enqueue_run(request: Request, run_id: UUID) -> bool:
    pool = getattr(request.app.state, "arq", None)
    if pool is None:
        return False
    try:
        await pool.enqueue_job("execute_run", str(run_id))
        return True
    except Exception:  # noqa: BLE001 - surface as a 503 instead of a 500
        return False


def define_run_read(run: Run) -> RunRead:
    return RunRead(
        id=run.id,
        project_id=run.project_id,
        workflow_key=run.workflow_key,
        preset_version_id=run.preset_version_id,
        status=run.status,
        mode=run.mode,
        current_node=run.current_node,
        error_code=run.error_code,
        error_message=run.error_message,
        input=run.input_json or {},
        created_at=run.created_at,
        started_at=run.started_at,
        ended_at=run.ended_at,
    )


@router.post(
    "/projects/{project_id}/runs",
    response_model=RunCreateResponse,
    status_code=202,
    operation_id="create_run",
)
async def create_run(
    project_id: UUID,
    payload: RunCreateRequest,
    request: Request,
    idempotency: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_db),
) -> RunCreateResponse:
    project = await _project_or_404(session, project_id)
    if payload.mode not in RUN_MODES:
        raise APIError("RUN_MODE_INVALID", f"Unsupported run mode '{payload.mode}'.", status_code=422)
    get_workflow(payload.workflow)

    service = RunService(session, request.app.state.settings)
    existing = await existing_action(session, "run.create", request)
    if existing is not None and existing.target_id is not None:
        run = await session.get(Run, existing.target_id)
        if run is not None:
            if run.status == "queued":
                await _enqueue_run(request, run.id)
            return _create_response(run)

    run, _reused = await service.create(
        project=project,
        workflow_key=payload.workflow,
        input_json=payload.input,
        mode=payload.mode,
        idempotency_key=idempotency_key(request),
        request_id=getattr(request.state, "request_id", None),
    )
    enqueued = await _enqueue_run(request, run.id)
    if not enqueued and run.status == "queued":
        # The run stays queued and can be picked up by a retry with the same
        # Idempotency-Key once the queue is reachable again.
        run = await service.mark_failed(
            run.id,
            code="RUN_ENQUEUE_FAILED",
            message="The run queue is unavailable; the run was not dispatched.",
        )
        raise APIError(
            "RUN_ENQUEUE_FAILED",
            "The run queue is unavailable.",
            status_code=503,
            details={"run_id": str(run.id)},
        )
    return _create_response(run)


def _create_response(run: Run) -> RunCreateResponse:
    return RunCreateResponse(
        run_id=run.id,
        status=run.status,
        links=RunLinks(
            self=f"/api/v1/runs/{run.id}",
            events=f"/api/v1/runs/{run.id}/events",
            stream=f"/api/v1/runs/{run.id}/events/stream",
        ),
    )


@router.get("/projects/{project_id}/runs", response_model=list[RunRead], operation_id="list_project_runs")
async def list_project_runs(
    project_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[RunRead]:
    await _project_or_404(session, project_id)
    service = RunService(session, request.app.state.settings)
    runs = await service.list_for_project(project_id, limit=limit)
    return [define_run_read(run) for run in runs]


@router.get("/runs/{run_id}", response_model=RunRead, operation_id="get_run")
async def get_run(run_id: UUID, session: AsyncSession = Depends(get_db)) -> RunRead:
    run = await session.get(Run, run_id)
    if run is None:
        raise APIError("RUN_NOT_FOUND", "The requested run does not exist.", status_code=404)
    return define_run_read(run)


@router.get("/runs/{run_id}/nodes", response_model=list[RunNodeRead], operation_id="list_run_nodes")
async def list_run_nodes(run_id: UUID, session: AsyncSession = Depends(get_db)) -> list[RunNode]:
    from sqlalchemy import select

    if await session.get(Run, run_id) is None:
        raise APIError("RUN_NOT_FOUND", "The requested run does not exist.", status_code=404)
    statement = select(RunNode).where(RunNode.run_id == run_id).order_by(RunNode.started_at.asc().nulls_last())
    return list((await session.execute(statement)).scalars().all())


@router.post("/runs/{run_id}:cancel", response_model=RunRead, operation_id="cancel_run")
async def cancel_run(
    run_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> RunRead:
    service = RunService(session, request.app.state.settings)
    existing = await existing_action(session, "run.cancel", request)
    if existing is not None and existing.target_id is not None:
        run = await session.get(Run, existing.target_id)
        if run is not None:
            return define_run_read(run)
    run = await service.cancel(run_id)
    record_action(session, action_type="run.cancel", target_type="run", target_id=run.id, request=request)
    await session.commit()
    return define_run_read(run)


@router.post("/runs/{run_id}:retry", response_model=RunCreateResponse, status_code=202, operation_id="retry_run")
async def retry_run(
    run_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> RunCreateResponse:
    service = RunService(session, request.app.state.settings)
    existing = await existing_action(session, "run.retry", request)
    if existing is not None and existing.target_id is not None:
        previous = await session.get(Run, existing.target_id)
        if previous is not None:
            await _enqueue_run(request, previous.id)
            return _create_response(previous)

    run, created_new = await service.retry(run_id)
    record_action(session, action_type="run.retry", target_type="run", target_id=run.id, request=request)
    await session.commit()
    enqueued = await _enqueue_run(request, run.id)
    if not enqueued:
        raise APIError(
            "RUN_ENQUEUE_FAILED",
            "The run queue is unavailable.",
            status_code=503,
            details={"run_id": str(run.id), "created_new": created_new},
        )
    return _create_response(run)


@router.get("/runs/{run_id}/events", response_model=RunEventsResponse, operation_id="list_run_events")
async def list_run_events(
    run_id: UUID,
    request: Request,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=2000),
    session: AsyncSession = Depends(get_db),
) -> RunEventsResponse:
    if await session.get(Run, run_id) is None:
        raise APIError("RUN_NOT_FOUND", "The requested run does not exist.", status_code=404)
    service = RunService(session, request.app.state.settings)
    events = await service.events_since(run_id, after_sequence=after, limit=limit)
    payloads = [event_payload(event) for event in events]
    return RunEventsResponse(
        run_id=run_id,
        events=payloads,
        last_sequence=payloads[-1]["sequence"] if payloads else after,
    )


@router.get("/runs/{run_id}/events/stream", operation_id="stream_run_events")
async def stream_run_events(
    run_id: UUID,
    request: Request,
    after: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Server-sent events for one run.

    Resumable: clients send `Last-Event-ID` (or `?after=`) to continue from the
    last sequence they saw. Ordering is the append-only `events.sequence`.
    """

    if await session.get(Run, run_id) is None:
        raise APIError("RUN_NOT_FOUND", "The requested run does not exist.", status_code=404)
    last_event_id = request.headers.get("Last-Event-ID")
    cursor = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from novel_agent.db.models import Event

    engine = request.app.state.db_engine
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def event_stream() -> AsyncIterator[str]:
        nonlocal cursor
        idle_polls = 0
        try:
            while True:
                if await request.is_disconnected():
                    break
                # Each poll owns a short-lived session: a long-lived streaming
                # session would hold a connection (and its transaction) for the
                # whole life of the stream.
                async with session_factory() as poll:
                    events = (
                        await poll.execute(
                            select(Event)
                            .where(Event.run_id == run_id, Event.sequence > cursor)
                            .order_by(Event.sequence.asc())
                            .limit(500)
                        )
                    ).scalars().all()
                    status = (
                        await poll.execute(select(Run.status).where(Run.id == run_id))
                    ).scalar_one_or_none()

                for event in events:
                    cursor = int(event.sequence)
                    yield to_sse(event)

                if status is None or (status in _TERMINAL and not events):
                    break
                idle_polls += 1
                if idle_polls % 30 == 0:
                    # Keep proxies from closing an idle stream.
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:  # client went away
            raise
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/workflows/{workflow_key}", response_model=QualityGateRead, operation_id="get_workflow_definition")
async def get_workflow_definition(workflow_key: str) -> QualityGateRead:
    definition = get_workflow(workflow_key)
    dag = definition.to_dag_json()
    return QualityGateRead(
        workflow_key=definition.key,
        schema_version=definition.schema_version,
        entry_node=dag["entry_node"],
        nodes=dag["nodes"],
    )


__all__ = ["router", "define_run_read", "_TERMINAL"]
