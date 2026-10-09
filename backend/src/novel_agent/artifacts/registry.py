"""Artifact registry: schema-validated, immutable, hash-addressed versions (spec §5.3, §6)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_agent.artifacts.schemas import ArtifactSchemaRegistry, ArtifactValidationError
from novel_agent.core.config import Settings
from novel_agent.core.errors import APIError
from novel_agent.db.models import Artifact, ArtifactEdge, Project
from novel_agent.domain.states import ensure_transition
from novel_agent.projects.filesystem import ProjectFilesystem
from novel_agent.tracing.events import (
    ARTIFACT_APPROVED,
    ARTIFACT_CREATED,
    ARTIFACT_REJECTED,
    ARTIFACT_SUPERSEDED,
    EventLog,
)


@dataclass(frozen=True)
class ArtifactDraft:
    """Content to register; the envelope fields are derived by the registry."""

    type: str
    content: dict[str, Any]
    producer: str
    status: str = "draft"
    provenance: dict[str, Any] = field(default_factory=dict)


def canonical_content_hash(artifact_type: str, schema_version: str, content: dict[str, Any]) -> str:
    """Hash only deterministic content.

    Run metadata (timestamps, UUIDs, provenance) is deliberately excluded so a
    recorded replay reproduces identical hashes (spec §16.2).
    """

    canonical = json.dumps(
        {"type": artifact_type, "schema_version": schema_version, "content": content},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ArtifactRegistry:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.filesystem = ProjectFilesystem(settings)
        self.schemas = ArtifactSchemaRegistry.from_settings(settings)
        self.events = EventLog(session)

    # ------------------------------------------------------------------ create
    async def create(
        self,
        *,
        project: Project,
        draft: ArtifactDraft,
        run_id: UUID | None = None,
        node_id: UUID | None = None,
        parent_id: UUID | None = None,
        relation: str = "derived_from",
        actor_type: str = "system",
        actor_id: str | None = None,
    ) -> Artifact:
        self.schemas.validate(draft.type, draft.content)
        schema_version = self.schemas.schema_version(draft.type)
        content_hash = canonical_content_hash(draft.type, schema_version, draft.content)

        parent: Artifact | None = None
        if parent_id is not None:
            parent = await self.session.get(Artifact, parent_id)
            if parent is None:
                raise APIError("ARTIFACT_NOT_FOUND", "The parent artifact does not exist.", status_code=404)
            if parent.project_id != project.id:
                raise APIError(
                    "ARTIFACT_PROJECT_MISMATCH",
                    "The parent artifact belongs to a different project.",
                    status_code=409,
                )
            await self._supersede(parent, actor_type=actor_type, actor_id=actor_id)

        artifact_id = _new_uuid()
        provenance = dict(draft.provenance or {})
        provenance.setdefault("input_artifact_ids", [])
        provenance.setdefault("context_item_ids", [])
        provenance.setdefault("llm_call_ids", [])

        relative_path = f"artifacts/{draft.type}/{artifact_id}.json"
        root = Path(project.root_path)
        envelope = {
            "artifact_id": str(artifact_id),
            "type": draft.type,
            "schema_version": schema_version,
            "project_id": str(project.id),
            "run_id": str(run_id) if run_id else None,
            "producer": draft.producer,
            "status": draft.status,
            "content": draft.content,
            "content_hash": content_hash,
            "provenance": provenance,
        }
        # Files are written before the row is committed: the filesystem is the
        # human-readable source of truth and DB/Git reconciliation is a saga.
        self.filesystem.write_json(root, relative_path, envelope)

        artifact = Artifact(
            id=artifact_id,
            project_id=project.id,
            run_id=run_id,
            type=draft.type,
            schema_version=schema_version,
            status=draft.status,
            producer=draft.producer,
            content_json=draft.content,
            provenance=provenance,
            content_hash=content_hash,
            file_path=relative_path,
            parent_id=parent.id if parent else None,
        )
        self.session.add(artifact)
        await self.session.flush()

        if parent is not None:
            await self._add_edge(parent.id, artifact.id, relation)
        for input_id in provenance.get("input_artifact_ids") or []:
            try:
                input_uuid = UUID(str(input_id))
            except (TypeError, ValueError):
                continue
            if input_uuid != artifact.id:
                await self._add_edge(input_uuid, artifact.id, "input")

        await self.events.emit(
            ARTIFACT_CREATED,
            project_id=project.id,
            run_id=run_id,
            node_id=node_id,
            actor_type=actor_type,
            actor_id=actor_id,
            payload={
                "artifact_id": str(artifact.id),
                "type": artifact.type,
                "status": artifact.status,
                "content_hash": artifact.content_hash,
                "file_path": artifact.file_path,
                "parent_id": str(parent.id) if parent else None,
                "producer": artifact.producer,
            },
        )
        return artifact

    async def _supersede(self, parent: Artifact, *, actor_type: str, actor_id: str | None) -> None:
        if parent.status == "superseded":
            return
        ensure_transition("artifact", parent.status, "superseded")
        parent.status = "superseded"
        await self.session.flush()
        await self.events.emit(
            ARTIFACT_SUPERSEDED,
            project_id=parent.project_id,
            run_id=parent.run_id,
            actor_type=actor_type,
            actor_id=actor_id,
            payload={"artifact_id": str(parent.id), "type": parent.type},
        )

    async def _add_edge(self, source_id: UUID, target_id: UUID, relation: str) -> None:
        existing = await self.session.get(ArtifactEdge, (source_id, target_id, relation))
        if existing is not None:
            return
        if await self.session.get(Artifact, source_id) is None:
            return
        self.session.add(ArtifactEdge(source_artifact_id=source_id, target_artifact_id=target_id, relation=relation))
        await self.session.flush()

    # ------------------------------------------------------------------- read
    async def get(self, artifact_id: UUID) -> Artifact:
        artifact = await self.session.get(Artifact, artifact_id)
        if artifact is None:
            raise APIError("ARTIFACT_NOT_FOUND", "The requested artifact does not exist.", status_code=404)
        return artifact

    async def list_for_project(
        self,
        project_id: UUID,
        *,
        artifact_type: str | None = None,
        status: str | None = None,
        run_id: UUID | None = None,
        limit: int = 200,
    ) -> Sequence[Artifact]:
        statement = select(Artifact).where(Artifact.project_id == project_id)
        if artifact_type:
            statement = statement.where(Artifact.type == artifact_type)
        if status:
            statement = statement.where(Artifact.status == status)
        if run_id:
            statement = statement.where(Artifact.run_id == run_id)
        statement = statement.order_by(Artifact.created_at.asc()).limit(limit)
        return (await self.session.execute(statement)).scalars().all()

    async def lineage(self, artifact_id: UUID) -> dict[str, list[dict[str, Any]]]:
        outgoing = (
            await self.session.execute(
                select(ArtifactEdge).where(ArtifactEdge.source_artifact_id == artifact_id)
            )
        ).scalars()
        incoming = (
            await self.session.execute(
                select(ArtifactEdge).where(ArtifactEdge.target_artifact_id == artifact_id)
            )
        ).scalars()
        return {
            "sources": [
                {"artifact_id": str(edge.source_artifact_id), "relation": edge.relation} for edge in incoming
            ],
            "targets": [
                {"artifact_id": str(edge.target_artifact_id), "relation": edge.relation} for edge in outgoing
            ],
        }

    async def latest_for_run(self, run_id: UUID, artifact_type: str) -> Artifact | None:
        statement = (
            select(Artifact)
            .where(Artifact.run_id == run_id, Artifact.type == artifact_type)
            .order_by(Artifact.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def lineage_tree(self, artifact_id: UUID) -> list[dict[str, Any]]:
        """Walk parents transitively using a recursive CTE over artifact_edges."""

        from sqlalchemy import text

        statement = text(
            """
            WITH RECURSIVE ancestors AS (
                SELECT source_artifact_id AS artifact_id, target_artifact_id AS child_id, relation, 1 AS depth
                FROM artifact_edges
                WHERE target_artifact_id = :artifact_id
                UNION ALL
                SELECT e.source_artifact_id, e.target_artifact_id, e.relation, a.depth + 1
                FROM artifact_edges e
                JOIN ancestors a ON e.target_artifact_id = a.artifact_id
                WHERE a.depth < 32
            )
            SELECT artifact_id, child_id, relation, depth FROM ancestors ORDER BY depth, artifact_id
            """
        )
        rows = (await self.session.execute(statement, {"artifact_id": artifact_id})).mappings().all()
        return [
            {
                "artifact_id": str(row["artifact_id"]),
                "child_id": str(row["child_id"]),
                "relation": row["relation"],
                "depth": int(row["depth"]),
            }
            for row in rows
        ]

    # ------------------------------------------------------------------ review
    async def approve(self, artifact_id: UUID, *, actor_type: str = "api", actor_id: str | None = None) -> Artifact:
        return await self._transition(artifact_id, "approved", ARTIFACT_APPROVED, actor_type, actor_id)

    async def reject(self, artifact_id: UUID, *, actor_type: str = "api", actor_id: str | None = None) -> Artifact:
        return await self._transition(artifact_id, "rejected", ARTIFACT_REJECTED, actor_type, actor_id)

    async def _transition(
        self,
        artifact_id: UUID,
        target: str,
        event_type: str,
        actor_type: str,
        actor_id: str | None,
    ) -> Artifact:
        artifact = await self.get(artifact_id)
        ensure_transition("artifact", artifact.status, target)
        artifact.status = target
        await self.session.flush()
        await self.events.emit(
            event_type,
            project_id=artifact.project_id,
            run_id=artifact.run_id,
            actor_type=actor_type,
            actor_id=actor_id,
            payload={"artifact_id": str(artifact.id), "type": artifact.type, "status": target},
        )
        return artifact

    async def artifacts_for_run(self, run_id: UUID) -> Sequence[Artifact]:
        statement = select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at.asc())
        return (await self.session.execute(statement)).scalars().all()

    async def approved_canon_patches(self, project_id: UUID) -> Sequence[Artifact]:
        statement = select(Artifact).where(
            Artifact.project_id == project_id,
            Artifact.type == "canon_patch",
            or_(Artifact.status == "approved", Artifact.status == "proposed"),
        )
        return (await self.session.execute(statement)).scalars().all()


def _new_uuid() -> UUID:
    from uuid import uuid4

    return uuid4()


def artifact_read(artifact: Artifact) -> dict[str, Any]:
    """Serialize an artifact for API responses (spec §6 envelope)."""

    return {
        "artifact_id": str(artifact.id),
        "type": artifact.type,
        "schema_version": artifact.schema_version,
        "project_id": str(artifact.project_id),
        "run_id": str(artifact.run_id) if artifact.run_id else None,
        "producer": artifact.producer,
        "status": artifact.status,
        "content": artifact.content_json,
        "content_hash": artifact.content_hash,
        "file_path": artifact.file_path,
        "parent_id": str(artifact.parent_id) if artifact.parent_id else None,
        "provenance": artifact.provenance or {},
        "created_at": _iso(artifact.created_at),
        "updated_at": _iso(artifact.updated_at),
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


__all__ = [
    "ArtifactDraft",
    "ArtifactRegistry",
    "ArtifactValidationError",
    "artifact_read",
    "canonical_content_hash",
]
