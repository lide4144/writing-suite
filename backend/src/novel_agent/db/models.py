from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from novel_agent.db.base import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("kind IN ('production', 'sandbox')", name="ck_projects_kind"),
        CheckConstraint("status IN ('active', 'archived')", name="ck_projects_status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="production", server_default="production")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    root_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    active_preset_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("preset_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelEndpoint(Base):
    __tablename__ = "model_endpoints"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ModelProfile(Base):
    __tablename__ = "model_profiles"
    __table_args__ = (UniqueConstraint("endpoint_id", "model_name", name="uq_model_profiles_endpoint_model"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    endpoint_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("model_endpoints.id", ondelete="CASCADE"))
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    defaults: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Preset(Base):
    __tablename__ = "presets"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PresetVersion(Base):
    __tablename__ = "preset_versions"
    __table_args__ = (UniqueConstraint("preset_id", "version", name="uq_preset_versions_preset_version"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    preset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("presets.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = (UniqueConstraint("action_type", "request_id", name="uq_actions_type_request"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False, default="api", server_default="api")
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowDefinition(Base):
    """Immutable DAG definition (spec §5.1)."""

    __tablename__ = "workflow_definitions"
    __table_args__ = (UniqueConstraint("workflow_key", "schema_version", name="uq_workflow_definitions_key_schema"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    preset_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("preset_versions.id", ondelete="CASCADE"), nullable=True
    )
    workflow_key: Mapped[str] = mapped_column(String(128), nullable=False)
    dag_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'waiting_approval', 'succeeded', 'failed', 'cancelled')",
            name="ck_runs_status",
        ),
        CheckConstraint("mode IN ('normal', 'replay_recorded', 'replay_live')", name="ck_runs_mode"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    workflow_key: Mapped[str] = mapped_column(String(128), nullable=False)
    preset_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("preset_versions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", server_default="queued")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="normal", server_default="normal")
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    current_node: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=_utcnow
    )


class RunNode(Base):
    __tablename__ = "run_nodes"
    __table_args__ = (
        UniqueConstraint("run_id", "node_key", "attempt", name="uq_run_nodes_run_node_attempt"),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped', 'cancelled')",
            name="ck_run_nodes_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"))
    node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    input_artifact_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    output_artifact_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=_utcnow
    )


class Event(Base):
    """Append-only event log; `sequence` gives SSE resumable ordering (spec §11)."""

    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=False), nullable=False, unique=True)
    project_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"))
    node_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("run_nodes.id", ondelete="CASCADE"))
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False, default="system", server_default="system")
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'proposed', 'approved', 'rejected', 'superseded')",
            name="ck_artifacts_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", server_default="draft")
    producer: Mapped[str] = mapped_column(String(64), nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=_utcnow
    )


class ArtifactEdge(Base):
    __tablename__ = "artifact_edges"

    source_artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True
    )
    target_artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True
    )
    relation: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"))
    node_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("run_nodes.id", ondelete="SET NULL"))
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model_profile_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ContextItem(Base):
    __tablename__ = "context_items"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    item_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LlmCallContext(Base):
    __tablename__ = "llm_call_context"

    llm_call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("llm_calls.id", ondelete="CASCADE"), primary_key=True
    )
    context_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("context_items.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

