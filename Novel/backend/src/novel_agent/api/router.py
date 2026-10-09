from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import yaml
from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from novel_agent.api.idempotency import (
    commit_or_conflict as _commit,
    existing_action as _existing_action,
    flush_or_conflict as _flush,
    idempotency_key as _idempotency_key,
    record_action as _record_action,
)
from novel_agent.api.schemas import (
    ModelEndpointCreate,
    ModelEndpointRead,
    ModelEndpointTestRead,
    ModelProfileCreate,
    ModelProfileRead,
    PresetApplyRequest,
    PresetCopyRequest,
    PresetCreate,
    PresetRead,
    PresetVersionCreate,
    PresetVersionRead,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)
from novel_agent.core.errors import APIError
from novel_agent.db.models import Action, ModelEndpoint, ModelProfile, Preset, PresetVersion, Project
from novel_agent.db.session import get_db
from novel_agent.presets.service import PresetValidationError, validate_preset_yaml
from novel_agent.projects.filesystem import ProjectFilesystem

logger = logging.getLogger(__name__)
api_router = APIRouter(prefix="/api/v1")
_PRESET_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,127}$")


def _idempotency_key_legacy(request: Request) -> str | None:  # retained for older internal callers
    return _idempotency_key(request)


async def _target_from_action(session: AsyncSession, action: Action | None, model: type[Any]) -> Any | None:
    if action is None or action.target_id is None:
        return None
    return await session.get(model, action.target_id)


def _preset_validation_error(exc: PresetValidationError) -> APIError:
    return APIError(
        "PRESET_VALIDATION_FAILED",
        str(exc),
        status_code=422,
        details=exc.details,
    )


def _validate_preset(raw_yaml: str, request: Request) -> tuple[dict[str, Any], str, str]:
    try:
        return validate_preset_yaml(raw_yaml, request.app.state.settings)
    except PresetValidationError as exc:
        raise _preset_validation_error(exc) from exc


def _validate_preset_name(name: str) -> None:
    if not _PRESET_NAME_PATTERN.fullmatch(name):
        raise APIError(
            "PRESET_NAME_INVALID",
            "Preset names must start with a lowercase letter and contain only lowercase letters, numbers, '_' or '-'.",
            status_code=422,
        )


async def _latest_preset_version(session: AsyncSession, preset_id: UUID) -> PresetVersion | None:
    return (
        await session.execute(
            select(PresetVersion)
            .where(PresetVersion.preset_id == preset_id)
            .order_by(desc(PresetVersion.version))
            .limit(1)
        )
    ).scalar_one_or_none()


def _preset_read(preset: Preset, latest: PresetVersion | None) -> PresetRead:
    return PresetRead(
        id=preset.id,
        name=preset.name,
        description=preset.description,
        latest_version=PresetVersionRead.model_validate(latest) if latest else None,
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


@api_router.get("/projects", response_model=list[ProjectRead], operation_id="list_projects")
async def list_projects(session: AsyncSession = Depends(get_db)) -> list[Project]:
    result = await session.execute(select(Project).order_by(desc(Project.created_at)).limit(200))
    return list(result.scalars().all())


@api_router.post("/projects", response_model=ProjectRead, status_code=201, operation_id="create_project")
async def create_project(
    payload: ProjectCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Project:
    action_type = "project.create"
    existing = await _existing_action(session, action_type, request)
    reused = await _target_from_action(session, existing, Project)
    if reused is not None:
        return reused

    project_id = uuid4()
    filesystem = ProjectFilesystem(request.app.state.settings)
    slug = filesystem.slugify(payload.slug or payload.name, fallback_id=project_id)
    existing_slug = (await session.execute(select(Project).where(Project.slug == slug))).scalar_one_or_none()
    if existing_slug is not None:
        raise APIError("PROJECT_SLUG_CONFLICT", "A project with this slug already exists.", status_code=409)

    preset_version: PresetVersion | None = None
    if payload.active_preset_version_id is not None:
        preset_version = await session.get(PresetVersion, payload.active_preset_version_id)
        if preset_version is None:
            raise APIError("PRESET_VERSION_NOT_FOUND", "The requested preset version does not exist.", status_code=404)

    root = filesystem.initialize(
        project_id=project_id,
        slug=slug,
        name=payload.name,
        kind=payload.kind,
        preset_version_id=preset_version.id if preset_version else None,
    )
    project = Project(
        id=project_id,
        slug=slug,
        name=payload.name,
        kind=payload.kind,
        status="active",
        root_path=str(root),
        active_preset_version_id=preset_version.id if preset_version else None,
    )
    session.add(project)
    _record_action(session, action_type=action_type, target_type="project", target_id=project.id, request=request)
    try:
        await _commit(session)
    except APIError:
        # Only remove a path whose manifest contains the UUID allocated above.
        manifest = root / "project.yaml"
        try:
            raw_manifest = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        except (FileNotFoundError, yaml.YAMLError):
            raw_manifest = None
        if isinstance(raw_manifest, dict) and raw_manifest.get("project_id") == str(project_id):
            import shutil

            shutil.rmtree(root, ignore_errors=True)
        raise
    await session.refresh(project)
    return project


@api_router.get("/projects/{project_id}", response_model=ProjectRead, operation_id="get_project")
async def get_project(project_id: UUID, session: AsyncSession = Depends(get_db)) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise APIError("PROJECT_NOT_FOUND", "The project does not exist.", status_code=404)
    return project


@api_router.patch("/projects/{project_id}", response_model=ProjectRead, operation_id="update_project")
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise APIError("PROJECT_NOT_FOUND", "The project does not exist.", status_code=404)
    action_type = "project.update"
    existing = await _existing_action(session, action_type, request)
    reused = await _target_from_action(session, existing, Project)
    if reused is not None:
        return reused
    if payload.name is not None and payload.name != project.name:
        filesystem = ProjectFilesystem(request.app.state.settings)
        filesystem.update_manifest(Path(project.root_path), {"name": payload.name})
        project.name = payload.name
    _record_action(session, action_type=action_type, target_type="project", target_id=project.id, request=request)
    await _commit(session)
    await session.refresh(project)
    return project


@api_router.post("/projects/{project_id}/archive", response_model=ProjectRead, operation_id="archive_project")
async def archive_project(
    project_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise APIError("PROJECT_NOT_FOUND", "The project does not exist.", status_code=404)
    action_type = "project.archive"
    existing = await _existing_action(session, action_type, request)
    reused = await _target_from_action(session, existing, Project)
    if reused is not None:
        return reused
    if project.status != "archived":
        project.status = "archived"
        project.archived_at = datetime.now(timezone.utc)
        ProjectFilesystem(request.app.state.settings).update_manifest(
            Path(project.root_path), {"status": "archived", "archived_at": project.archived_at.isoformat()}
        )
    _record_action(session, action_type=action_type, target_type="project", target_id=project.id, request=request)
    await _commit(session)
    await session.refresh(project)
    return project


@api_router.post("/projects/{project_id}/preset:apply", response_model=ProjectRead, operation_id="apply_project_preset")
async def apply_project_preset(
    project_id: UUID,
    payload: PresetApplyRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise APIError("PROJECT_NOT_FOUND", "The project does not exist.", status_code=404)
    if project.status == "archived":
        raise APIError("PROJECT_ARCHIVED", "An archived project cannot receive a new preset.", status_code=409)
    preset_version = await session.get(PresetVersion, payload.preset_version_id)
    if preset_version is None:
        raise APIError("PRESET_VERSION_NOT_FOUND", "The requested preset version does not exist.", status_code=404)
    action_type = "project.preset.apply"
    existing = await _existing_action(session, action_type, request)
    reused = await _target_from_action(session, existing, Project)
    if reused is not None:
        return reused
    project.active_preset_version_id = preset_version.id
    ProjectFilesystem(request.app.state.settings).update_manifest(
        Path(project.root_path), {"active_preset_version_id": str(preset_version.id)}
    )
    _record_action(session, action_type=action_type, target_type="project", target_id=project.id, request=request)
    await _commit(session)
    await session.refresh(project)
    return project


@api_router.get("/model-endpoints", response_model=list[ModelEndpointRead], operation_id="list_model_endpoints")
async def list_model_endpoints(session: AsyncSession = Depends(get_db)) -> list[ModelEndpoint]:
    result = await session.execute(select(ModelEndpoint).order_by(ModelEndpoint.name))
    return list(result.scalars().all())


@api_router.post(
    "/model-endpoints", response_model=ModelEndpointRead, status_code=201, operation_id="create_model_endpoint"
)
async def create_model_endpoint(
    payload: ModelEndpointCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ModelEndpoint:
    action_type = "model_endpoint.create"
    existing = await _existing_action(session, action_type, request)
    reused = await _target_from_action(session, existing, ModelEndpoint)
    if reused is not None:
        return reused
    endpoint = ModelEndpoint(
        name=payload.name,
        provider_type=payload.provider_type,
        base_url=str(payload.base_url).rstrip("/"),
        secret_ref=payload.secret_ref,
        capabilities=payload.capabilities,
        enabled=payload.enabled,
    )
    session.add(endpoint)
    await _flush(session)
    _record_action(session, action_type=action_type, target_type="model_endpoint", target_id=endpoint.id, request=request)
    await _commit(session)
    await session.refresh(endpoint)
    return endpoint


@api_router.post(
    "/model-endpoints/{endpoint_id}:test",
    response_model=ModelEndpointTestRead,
    operation_id="test_model_endpoint",
)
async def test_model_endpoint(endpoint_id: UUID, session: AsyncSession = Depends(get_db)) -> ModelEndpointTestRead:
    endpoint = await session.get(ModelEndpoint, endpoint_id)
    if endpoint is None:
        raise APIError("MODEL_ENDPOINT_NOT_FOUND", "The model endpoint does not exist.", status_code=404)
    headers: dict[str, str] = {}
    if endpoint.secret_ref:
        secret = os.getenv(endpoint.secret_ref)
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
    models_url = f"{endpoint.base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0), follow_redirects=True) as client:
            response = await client.get(models_url, headers=headers)
    except httpx.HTTPError:
        return ModelEndpointTestRead(status="unreachable", message="The endpoint could not be reached.")
    if 200 <= response.status_code < 300:
        return ModelEndpointTestRead(status="ok", http_status=response.status_code, message="Endpoint is healthy.")
    if response.status_code in {401, 403}:
        return ModelEndpointTestRead(
            status="reachable", http_status=response.status_code, message="Endpoint is reachable but authentication failed."
        )
    return ModelEndpointTestRead(
        status="reachable", http_status=response.status_code, message="Endpoint responded with a non-success status."
    )


@api_router.get("/model-profiles", response_model=list[ModelProfileRead], operation_id="list_model_profiles")
async def list_model_profiles(session: AsyncSession = Depends(get_db)) -> list[ModelProfile]:
    result = await session.execute(select(ModelProfile).order_by(ModelProfile.model_name))
    return list(result.scalars().all())


@api_router.post(
    "/model-profiles", response_model=ModelProfileRead, status_code=201, operation_id="create_model_profile"
)
async def create_model_profile(
    payload: ModelProfileCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ModelProfile:
    endpoint = await session.get(ModelEndpoint, payload.endpoint_id)
    if endpoint is None:
        raise APIError("MODEL_ENDPOINT_NOT_FOUND", "The model endpoint does not exist.", status_code=404)
    action_type = "model_profile.create"
    existing = await _existing_action(session, action_type, request)
    reused = await _target_from_action(session, existing, ModelProfile)
    if reused is not None:
        return reused
    profile = ModelProfile(
        endpoint_id=payload.endpoint_id,
        model_name=payload.model_name,
        defaults=payload.defaults,
        capabilities=payload.capabilities,
    )
    session.add(profile)
    await _flush(session)
    _record_action(session, action_type=action_type, target_type="model_profile", target_id=profile.id, request=request)
    await _commit(session)
    await session.refresh(profile)
    return profile


@api_router.get("/presets", response_model=list[PresetRead], operation_id="list_presets")
async def list_presets(session: AsyncSession = Depends(get_db)) -> list[PresetRead]:
    presets = list((await session.execute(select(Preset).order_by(Preset.name))).scalars().all())
    return [_preset_read(preset, await _latest_preset_version(session, preset.id)) for preset in presets]


@api_router.get("/presets/{preset_id}", response_model=PresetRead, operation_id="get_preset")
async def get_preset(preset_id: UUID, session: AsyncSession = Depends(get_db)) -> PresetRead:
    preset = await session.get(Preset, preset_id)
    if preset is None:
        raise APIError("PRESET_NOT_FOUND", "The preset does not exist.", status_code=404)
    return _preset_read(preset, await _latest_preset_version(session, preset.id))


@api_router.post("/presets", response_model=PresetRead, status_code=201, operation_id="create_preset")
async def create_preset(
    payload: PresetCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PresetRead:
    _validate_preset_name(payload.name)
    action_type = "preset.create"
    existing = await _existing_action(session, action_type, request)
    reused = await _target_from_action(session, existing, Preset)
    if reused is not None:
        return _preset_read(reused, await _latest_preset_version(session, reused.id))
    version_data: tuple[dict[str, Any], str, str] | None = None
    if payload.content_yaml is not None:
        version_data = _validate_preset(payload.content_yaml, request)
        if version_data[0].get("name") != payload.name:
            raise APIError("PRESET_NAME_MISMATCH", "Preset YAML name must match the preset resource name.", status_code=422)
    preset = Preset(name=payload.name, description=payload.description)
    session.add(preset)
    await _flush(session)
    if version_data is not None:
        content, schema_version, content_hash = version_data
        session.add(
            PresetVersion(
                preset_id=preset.id,
                version=1,
                content_yaml=payload.content_yaml or "",
                content_json=content,
                content_hash=content_hash,
                schema_version=schema_version,
            )
        )
    _record_action(session, action_type=action_type, target_type="preset", target_id=preset.id, request=request)
    await _commit(session)
    await session.refresh(preset)
    return _preset_read(preset, await _latest_preset_version(session, preset.id))


@api_router.get("/presets/{preset_id}/versions/{version}", response_model=PresetVersionRead, operation_id="get_preset_version")
async def get_preset_version(
    preset_id: UUID, version: int, session: AsyncSession = Depends(get_db)
) -> PresetVersion:
    preset_version = (
        await session.execute(
            select(PresetVersion).where(PresetVersion.preset_id == preset_id, PresetVersion.version == version)
        )
    ).scalar_one_or_none()
    if preset_version is None:
        raise APIError("PRESET_VERSION_NOT_FOUND", "The requested preset version does not exist.", status_code=404)
    return preset_version


@api_router.post(
    "/presets/{preset_id}/versions",
    response_model=PresetVersionRead,
    status_code=201,
    operation_id="create_preset_version",
)
async def create_preset_version(
    preset_id: UUID,
    payload: PresetVersionCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PresetVersion:
    preset = await session.get(Preset, preset_id)
    if preset is None:
        raise APIError("PRESET_NOT_FOUND", "The preset does not exist.", status_code=404)
    action_type = "preset.version.create"
    existing = await _existing_action(session, action_type, request)
    reused = await _target_from_action(session, existing, PresetVersion)
    if reused is not None:
        return reused
    content, schema_version, content_hash = _validate_preset(payload.content_yaml, request)
    if content.get("name") != preset.name:
        raise APIError("PRESET_NAME_MISMATCH", "Preset YAML name must match the preset resource name.", status_code=422)
    current_max = await session.scalar(select(func.max(PresetVersion.version)).where(PresetVersion.preset_id == preset_id))
    next_version = payload.version or ((current_max or 0) + 1)
    if next_version <= (current_max or 0):
        raise APIError("PRESET_VERSION_IMMUTABLE", "A preset version number cannot be reused.", status_code=409)
    preset_version = PresetVersion(
        preset_id=preset_id,
        version=next_version,
        content_yaml=payload.content_yaml,
        content_json=content,
        content_hash=content_hash,
        schema_version=schema_version,
    )
    session.add(preset_version)
    await _flush(session)
    _record_action(
        session, action_type=action_type, target_type="preset_version", target_id=preset_version.id, request=request
    )
    await _commit(session)
    await session.refresh(preset_version)
    return preset_version


@api_router.post("/presets/{preset_id}/versions/{version}:copy", response_model=PresetRead, status_code=201, operation_id="copy_preset")
async def copy_preset(
    preset_id: UUID,
    version: int,
    payload: PresetCopyRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PresetRead:
    _validate_preset_name(payload.name)
    source = (
        await session.execute(
            select(PresetVersion).where(PresetVersion.preset_id == preset_id, PresetVersion.version == version)
        )
    ).scalar_one_or_none()
    if source is None:
        raise APIError("PRESET_VERSION_NOT_FOUND", "The requested preset version does not exist.", status_code=404)
    action_type = "preset.copy"
    existing = await _existing_action(session, action_type, request)
    reused = await _target_from_action(session, existing, Preset)
    if reused is not None:
        return _preset_read(reused, await _latest_preset_version(session, reused.id))
    content = dict(source.content_json)
    content["name"] = payload.name
    copied_yaml = yaml.safe_dump(content, allow_unicode=True, sort_keys=False)
    validated_content, schema_version, content_hash = _validate_preset(copied_yaml, request)
    preset = Preset(name=payload.name, description=payload.description)
    session.add(preset)
    await _flush(session)
    session.add(
        PresetVersion(
            preset_id=preset.id,
            version=1,
            content_yaml=copied_yaml,
            content_json=validated_content,
            content_hash=content_hash,
            schema_version=schema_version,
        )
    )
    _record_action(session, action_type=action_type, target_type="preset", target_id=preset.id, request=request)
    await _commit(session)
    await session.refresh(preset)
    return _preset_read(preset, await _latest_preset_version(session, preset.id))


# M2 routers (runs/workflow, artifacts, diagnostics and debug reads).
from novel_agent.api import artifacts as _artifacts_api  # noqa: E402
from novel_agent.api import debug as _debug_api  # noqa: E402
from novel_agent.api import runs as _runs_api  # noqa: E402

api_router.include_router(_runs_api.router)
api_router.include_router(_artifacts_api.router)
api_router.include_router(_debug_api.router)
