"""Artifact endpoints: list, read, lineage, approve and reject (spec §10.1)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from novel_agent.api.idempotency import existing_action, record_action
from novel_agent.api.schemas import ArtifactLineageRead, ArtifactRead
from novel_agent.artifacts.registry import ArtifactRegistry, artifact_read
from novel_agent.core.errors import APIError
from novel_agent.db.models import Artifact, Project, Run
from novel_agent.db.session import get_db
from novel_agent.workflows.service import RunService

router = APIRouter(tags=["artifacts"])


async def _resume_run_after_decision(request: Request, session: AsyncSession, artifact: Artifact) -> None:
    """Approving or rejecting a canon patch resumes the waiting run (spec §8)."""

    if artifact.type != "canon_patch" or artifact.run_id is None:
        return
    run = await session.get(Run, artifact.run_id)
    if run is None or run.status != "waiting_approval":
        return
    service = RunService(session, request.app.state.settings)
    await service.retry(run.id, actor_type="api", actor_id=None)
    pool = getattr(request.app.state, "arq", None)
    if pool is not None:
        await pool.enqueue_job("execute_run", str(run.id))


@router.get(
    "/projects/{project_id}/artifacts",
    response_model=list[ArtifactRead],
    operation_id="list_project_artifacts",
)
async def list_project_artifacts(
    project_id: UUID,
    request: Request,
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    run_id: UUID | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    if await session.get(Project, project_id) is None:
        raise APIError("PROJECT_NOT_FOUND", "The requested project does not exist.", status_code=404)
    registry = ArtifactRegistry(session, request.app.state.settings)
    artifacts = await registry.list_for_project(
        project_id, artifact_type=type, status=status, run_id=run_id, limit=limit
    )
    return [artifact_read(artifact) for artifact in artifacts]


@router.get("/artifacts/{artifact_id}", response_model=ArtifactRead, operation_id="get_artifact")
async def get_artifact(
    artifact_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    registry = ArtifactRegistry(session, request.app.state.settings)
    artifact = await registry.get(artifact_id)
    return artifact_read(artifact)


@router.get(
    "/artifacts/{artifact_id}/lineage",
    response_model=ArtifactLineageRead,
    operation_id="get_artifact_lineage",
)
async def get_artifact_lineage(
    artifact_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ArtifactLineageRead:
    registry = ArtifactRegistry(session, request.app.state.settings)
    artifact = await registry.get(artifact_id)
    lineage = await registry.lineage(artifact_id)
    ancestors = await registry.lineage_tree(artifact_id)
    return ArtifactLineageRead(
        artifact_id=artifact.id,
        sources=lineage["sources"],
        targets=lineage["targets"],
        ancestors=ancestors,
    )


@router.post("/artifacts/{artifact_id}:approve", response_model=ArtifactRead, operation_id="approve_artifact")
async def approve_artifact(
    artifact_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    existing = await existing_action(session, "artifact.approve", request)
    if existing is not None and existing.target_id is not None:
        artifact = await session.get(Artifact, existing.target_id)
        if artifact is not None:
            return artifact_read(artifact)
    registry = ArtifactRegistry(session, request.app.state.settings)
    artifact = await registry.approve(artifact_id)
    record_action(session, action_type="artifact.approve", target_type="artifact", target_id=artifact.id, request=request)
    await session.commit()
    await _resume_run_after_decision(request, session, artifact)
    return artifact_read(artifact)


@router.post("/artifacts/{artifact_id}:reject", response_model=ArtifactRead, operation_id="reject_artifact")
async def reject_artifact(
    artifact_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    existing = await existing_action(session, "artifact.reject", request)
    if existing is not None and existing.target_id is not None:
        artifact = await session.get(Artifact, existing.target_id)
        if artifact is not None:
            return artifact_read(artifact)
    registry = ArtifactRegistry(session, request.app.state.settings)
    artifact = await registry.reject(artifact_id)
    record_action(session, action_type="artifact.reject", target_type="artifact", target_id=artifact.id, request=request)
    await session.commit()
    await _resume_run_after_decision(request, session, artifact)
    return artifact_read(artifact)


__all__ = ["router"]
