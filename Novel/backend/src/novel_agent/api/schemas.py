from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=255)
    kind: Literal["production", "sandbox"] = "production"
    active_preset_version_id: UUID | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    kind: Literal["production", "sandbox"]
    status: Literal["active", "archived"]
    root_path: str
    active_preset_version_id: UUID | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ModelEndpointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider_type: str = Field(default="openai_compatible", min_length=1, max_length=64)
    base_url: AnyHttpUrl
    secret_ref: str | None = Field(default=None, max_length=255)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ModelEndpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    provider_type: str
    base_url: str
    secret_ref: str | None
    capabilities: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ModelProfileCreate(BaseModel):
    endpoint_id: UUID
    model_name: str = Field(min_length=1, max_length=255)
    defaults: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class ModelProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    endpoint_id: UUID
    model_name: str
    defaults: dict[str, Any]
    capabilities: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PresetVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    preset_id: UUID
    version: int
    content_yaml: str
    content_json: dict[str, Any]
    content_hash: str
    schema_version: str
    created_at: datetime


class PresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    content_yaml: str | None = None


class PresetVersionCreate(BaseModel):
    content_yaml: str = Field(min_length=1)
    version: int | None = Field(default=None, ge=1)


class PresetCopyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None


class PresetRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    latest_version: PresetVersionRead | None = None
    created_at: datetime
    updated_at: datetime


class PresetApplyRequest(BaseModel):
    preset_version_id: UUID


class ModelEndpointTestRead(BaseModel):
    status: Literal["ok", "reachable", "unreachable"]
    http_status: int | None = None
    message: str


# --------------------------------------------------------------------- M2 runs


class RunCreateRequest(BaseModel):
    workflow: str = Field(default="chapter_generation", min_length=1, max_length=128)
    input: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["normal", "replay_recorded", "replay_live"] = "normal"


class RunLinks(BaseModel):
    self: str
    events: str
    stream: str


class RunCreateResponse(BaseModel):
    run_id: UUID
    status: str
    links: RunLinks


class RunRead(BaseModel):
    id: UUID
    project_id: UUID
    workflow_key: str
    preset_version_id: UUID | None
    status: str
    mode: str
    current_node: str | None
    error_code: str | None
    error_message: str | None
    input: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None


class RunNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_key: str
    attempt: int
    status: str
    input_artifact_ids: list[Any]
    output_artifact_ids: list[Any]
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    ended_at: datetime | None


class RunEventRead(BaseModel):
    id: UUID
    sequence: int
    project_id: UUID | None
    run_id: UUID | None
    node_id: UUID | None
    actor_type: str
    actor_id: str | None
    event_type: str
    payload: dict[str, Any]
    created_at: datetime | None


class RunEventsResponse(BaseModel):
    run_id: UUID
    events: list[RunEventRead]
    last_sequence: int


class ArtifactRead(BaseModel):
    artifact_id: UUID
    type: str
    schema_version: str
    project_id: UUID
    run_id: UUID | None
    producer: str
    status: str
    content: dict[str, Any]
    content_hash: str
    file_path: str | None
    parent_id: UUID | None
    provenance: dict[str, Any]
    created_at: datetime | None
    updated_at: datetime | None


class ArtifactLineageRead(BaseModel):
    artifact_id: UUID
    sources: list[dict[str, Any]]
    targets: list[dict[str, Any]]
    ancestors: list[dict[str, Any]]


class LlmCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID | None
    node_id: UUID | None
    agent_key: str
    model_profile_snapshot: dict[str, Any]
    request_json: dict[str, Any]
    response_json: dict[str, Any] | None
    usage_json: dict[str, Any]
    latency_ms: int | None
    status: str
    error: str | None
    created_at: datetime


class DiagnosticsComponent(BaseModel):
    status: Literal["ok", "error"]
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class DiagnosticsResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    components: dict[str, DiagnosticsComponent]
    timestamp: datetime


class DebugTraceResponse(BaseModel):
    run: RunRead
    nodes: list[RunNodeRead]
    artifacts: list[ArtifactRead]
    events: list[RunEventRead]
    llm_calls: list[LlmCallRead]
    errors: list[dict[str, Any]]


class QualityGateRead(BaseModel):
    workflow_key: str
    schema_version: str
    entry_node: str
    nodes: list[dict[str, Any]]
