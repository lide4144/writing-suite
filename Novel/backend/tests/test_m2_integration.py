"""M2 integration tests: real PostgreSQL, the workflow runtime and the fake provider.

These cover the §17 M2 acceptance criteria: a complete simulated workflow without
a real LLM, plus testable cancellation and failure branches.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from novel_agent.artifacts.registry import ArtifactRegistry, canonical_content_hash
from novel_agent.core.errors import APIError
from novel_agent.db.models import Artifact, Event, LlmCall, Project, Run, RunNode
from novel_agent.domain.states import IllegalStateTransition
from novel_agent.projects.filesystem import ProjectFilesystem
from novel_agent.providers.factory import MODE_REPLAY_RECORDED, build_provider
from novel_agent.providers.fake import FakeProvider, FakeScenario
from novel_agent.tracing.events import REQUIRED_EVENT_TYPES
from novel_agent.workflows.runner import RunExecutor
from novel_agent.workflows.service import RunService

pytestmark = pytest.mark.integration

REQUIRED_ARTIFACT_TYPES = {
    "director_decision",
    "plot_plan",
    "idea_candidates",
    "character_intent",
    "scene_brief",
    "chapter_draft",
    "continuity_report",
    "critic_report",
    "style_edit_result",
    "canon_patch",
    "chapter_summary",
}

AGENT_NODE_KEYS = {
    "director",
    "plot_architect",
    "idea",
    "character",
    "scene_planner",
    "writer",
    "continuity",
    "critic",
    "style_editor",
    "canon_extractor",
}


async def make_project(session, settings, *, kind: str = "sandbox", name: str = "Test Novel") -> Project:
    project_id = uuid4()
    filesystem = ProjectFilesystem(settings)
    slug = filesystem.slugify(f"{name} {project_id.hex[:8]}")
    root = filesystem.initialize(
        project_id=project_id, slug=slug, name=name, kind=kind, preset_version_id=None
    )
    project = Project(
        id=project_id,
        slug=slug,
        name=name,
        kind=kind,
        status="active",
        root_path=str(root),
    )
    session.add(project)
    await session.commit()
    return project


async def execute_run(
    session,
    settings,
    project: Project,
    *,
    scenario: FakeScenario | None = None,
    faults_by_agent: dict[str, list[str]] | None = None,
    mode: str = "normal",
    input_json: dict | None = None,
    provider=None,
) -> tuple[Run, FakeProvider | None]:
    service = RunService(session, settings)
    run, _ = await service.create(
        project=project,
        workflow_key="chapter_generation",
        input_json=input_json or {"chapter_number": 1},
        mode=mode,
    )
    fake = provider
    if fake is None and mode == "normal":
        fake = FakeProvider(
            scenario=scenario or FakeScenario(),
            faults_by_agent=faults_by_agent,
            chapter_number=1,
        )
    resolved = fake or await build_provider(session, settings, run)
    executor = RunExecutor(session, settings, resolved)
    executed = await executor.execute(run.id)
    return executed, fake


async def node_rows(session, run_id: UUID) -> list[RunNode]:
    return list(
        (
            await session.execute(
                select(RunNode).where(RunNode.run_id == run_id).order_by(RunNode.started_at.asc().nulls_last())
            )
        )
        .scalars()
        .all()
    )


async def artifact_rows(session, run_id: UUID) -> list[Artifact]:
    return list(
        (await session.execute(select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at.asc())))
        .scalars()
        .all()
    )


async def event_types(session, run_id: UUID) -> list[str]:
    return list(
        (await session.execute(select(Event.event_type).where(Event.run_id == run_id).order_by(Event.sequence.asc())))
        .scalars()
        .all()
    )


# --------------------------------------------------------------------- happy path
async def test_full_chapter_workflow_succeeds_without_a_real_llm(session, integration_settings) -> None:
    project = await make_project(session, integration_settings)
    run, provider = await execute_run(session, integration_settings, project)

    assert run.status == "succeeded", run.error_message
    assert run.current_node == "canon_manager"

    artifacts = await artifact_rows(session, run.id)
    assert REQUIRED_ARTIFACT_TYPES <= {artifact.type for artifact in artifacts}
    for artifact in artifacts:
        assert artifact.status in {"draft", "approved", "proposed"}
        assert artifact.content_hash == canonical_content_hash(
            artifact.type, artifact.schema_version, artifact.content_json
        )
        assert artifact.file_path is not None
        assert (Path(project.root_path) / artifact.file_path).is_file()

    events = await event_types(session, run.id)
    happy_path_events = {
        "run.queued",
        "run.started",
        "node.started",
        "llm_call.started",
        "llm_call.completed",
        "artifact.created",
        "node.completed",
        "run.completed",
    }
    assert happy_path_events <= set(events), sorted(happy_path_events - set(events))

    nodes = await node_rows(session, run.id)
    by_key = {node.node_key: node for node in nodes}
    assert {"director", "writer", "continuity", "critic", "quality_gate", "style_editor", "canon_manager"} <= set(
        by_key
    )
    # branch-only nodes exist as pending rows but are marked skipped when unused
    assert by_key["revision"].status == "skipped"
    assert by_key["keep_draft"].status == "skipped"

    calls = (await session.execute(select(LlmCall).where(LlmCall.run_id == run.id))).scalars().all()
    agent_nodes = [node for node in nodes if node.node_key in AGENT_NODE_KEYS]
    # One call per agent node, plus the summarizer call made by the commit node.
    assert len(calls) == len(agent_nodes) + 1
    assert {call.node_id for call in calls if call.node_id is not None} >= {node.id for node in agent_nodes}
    assert all(call.status == "succeeded" for call in calls)
    assert all(call.request_json for call in calls)
    assert all("temperature" in (call.request_json.get("params") or {}) for call in calls)

    chapter_dir = Path(project.root_path) / "chapters" / "0001"
    for name in ("brief.json", "draft.md", "final.md", "summary.md"):
        assert (chapter_dir / name).is_file(), name

    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"], cwd=project.root_path, capture_output=True, text=True, check=True
    ).stdout
    assert f"Run-Id: {run.id}" in log
    assert "Artifact-Ids:" in log


async def test_canon_patch_applied_to_project_canon(session, integration_settings) -> None:
    project = await make_project(session, integration_settings)
    await execute_run(session, integration_settings, project)
    facts = (Path(project.root_path) / "canon" / "facts.yaml").read_text(encoding="utf-8")
    assert "archive_room_has_no_window" in facts


async def test_every_required_event_type_is_reachable(session, integration_settings) -> None:
    """§11 requires at least these event types; each must be emitted by some branch."""

    observed: set[str] = set()

    success_project = await make_project(session, integration_settings, name="Event Success")
    success_run, _ = await execute_run(session, integration_settings, success_project)
    observed.update(await event_types(session, success_run.id))

    escalate_project = await make_project(session, integration_settings, name="Event Escalate")
    escalate_run, _ = await execute_run(
        session,
        integration_settings,
        escalate_project,
        scenario=FakeScenario(continuity_scores=[0.4]),
    )
    assert escalate_run.status == "waiting_approval"
    observed.update(await event_types(session, escalate_run.id))

    failed_project = await make_project(session, integration_settings, name="Event Failure")
    failed_run, _ = await execute_run(
        session,
        integration_settings,
        failed_project,
        faults_by_agent={"writer": ["malformed_json"]},
    )
    assert failed_run.status == "failed"
    observed.update(await event_types(session, failed_run.id))

    assert set(REQUIRED_EVENT_TYPES) <= observed, sorted(set(REQUIRED_EVENT_TYPES) - observed)


# ------------------------------------------------------------------ revision loop
async def test_quality_gate_failure_triggers_revision_and_passes_on_second_attempt(
    session, integration_settings
) -> None:
    project = await make_project(session, integration_settings)
    scenario = FakeScenario(continuity_scores=[0.5, 0.99])
    run, _ = await execute_run(session, integration_settings, project, scenario=scenario)

    assert run.status == "succeeded", run.error_message
    nodes = await node_rows(session, run.id)
    assert [node.node_key for node in nodes].count("revision") == 1
    gates = [node for node in nodes if node.node_key == "quality_gate"]
    assert len(gates) == 2

    drafts = [artifact for artifact in await artifact_rows(session, run.id) if artifact.type == "chapter_draft"]
    assert len(drafts) == 2
    first, second = drafts
    assert first.status == "superseded"
    assert second.parent_id == first.id
    assert "quality_gate.failed" in await event_types(session, run.id)


async def test_revision_limit_escalates_to_waiting_approval(session, integration_settings) -> None:
    project = await make_project(session, integration_settings)
    scenario = FakeScenario(continuity_scores=[0.4], hard_failures=[["required_fact_missing"]])
    run, _ = await execute_run(session, integration_settings, project, scenario=scenario)

    assert run.status == "waiting_approval"
    nodes = await node_rows(session, run.id)
    by_key: dict[str, list[RunNode]] = {}
    for node in nodes:
        by_key.setdefault(node.node_key, []).append(node)
    assert len(by_key["revision"]) == 3
    assert len(by_key["quality_gate"]) == 4
    # §8: revision loops back into Continuity + Critic before the gate re-runs
    assert len(by_key["continuity"]) == 4
    assert len(by_key["critic"]) == 4
    events = await event_types(session, run.id)
    assert events.count("quality_gate.failed") == 4
    assert "run.waiting_approval" in events
    # waiting_approval is a pause: later nodes stay pending, not skipped.
    assert all(node.status == "pending" for node in by_key["style_editor"])


# --------------------------------------------------------------- failure branches
async def test_transient_provider_failure_retries_then_fails_the_run(session, integration_settings) -> None:
    project = await make_project(session, integration_settings)
    run, _ = await execute_run(
        session,
        integration_settings,
        project,
        faults_by_agent={"writer": ["server_error", "server_error", "server_error"]},
    )

    assert run.status == "failed"
    assert run.error_code == "provider_server_error"
    writer_nodes = [node for node in await node_rows(session, run.id) if node.node_key == "writer"]
    assert [node.attempt for node in writer_nodes] == [1, 2]
    assert all(node.status == "failed" for node in writer_nodes)
    events = await event_types(session, run.id)
    assert "node.retry_scheduled" in events
    assert "run.failed" in events

    failed_calls = (
        await session.execute(select(LlmCall).where(LlmCall.run_id == run.id, LlmCall.status == "failed"))
    ).scalars().all()
    assert len(failed_calls) == 2


async def test_non_retryable_provider_failure_does_not_retry(session, integration_settings) -> None:
    project = await make_project(session, integration_settings)
    run, _ = await execute_run(
        session, integration_settings, project, faults_by_agent={"writer": ["malformed_json"]}
    )

    assert run.status == "failed"
    assert run.error_code == "provider_malformed_response"
    writer_nodes = [node for node in await node_rows(session, run.id) if node.node_key == "writer"]
    assert len(writer_nodes) == 1
    assert "node.retry_scheduled" not in await event_types(session, run.id)


# -------------------------------------------------------------------- cancellation
class CancelAfterWriterProvider(FakeProvider):
    """Cancels the run as soon as the writer node produced its draft."""

    def __init__(self, session, **kwargs) -> None:
        super().__init__(**kwargs)
        self._session = session

    async def complete(self, request):  # type: ignore[override]
        response = await super().complete(request)
        if request.agent_key == "writer":
            run = (
                await self._session.execute(select(Run).order_by(Run.created_at.desc()).limit(1))
            ).scalar_one()
            run.status = "cancelled"
            await self._session.commit()
        return response


async def test_cancellation_stops_the_run_and_propagates_to_nodes(session, integration_settings) -> None:
    project = await make_project(session, integration_settings)
    provider = CancelAfterWriterProvider(session, scenario=FakeScenario(), chapter_number=1)
    run, _ = await execute_run(session, integration_settings, project, provider=provider)

    assert run.status == "cancelled"
    events = await event_types(session, run.id)
    assert "run.cancelled" in events
    assert "run.completed" not in events
    nodes = await node_rows(session, run.id)
    by_key = {node.node_key: node for node in nodes}
    # Cancellation propagates: nodes after the writer were marked cancelled.
    assert by_key["continuity"].status == "cancelled"
    assert by_key["canon_manager"].status == "cancelled"
    cancelled = (
        await session.execute(select(RunNode).where(RunNode.run_id == run.id, RunNode.status == "cancelled"))
    ).scalars().all()
    assert len(cancelled) >= 5


# --------------------------------------------------------------------- idempotency
async def test_idempotency_key_reuses_the_same_run(session, integration_settings) -> None:
    project = await make_project(session, integration_settings)
    service = RunService(session, integration_settings)
    first, reused_first = await service.create(
        project=project,
        workflow_key="chapter_generation",
        input_json={"chapter_number": 1},
        idempotency_key="run-key-1",
    )
    second, reused_second = await service.create(
        project=project,
        workflow_key="chapter_generation",
        input_json={"chapter_number": 1},
        idempotency_key="run-key-1",
    )

    assert reused_first is False and reused_second is True
    assert first.id == second.id
    runs = (await session.execute(select(Run).where(Run.project_id == project.id))).scalars().all()
    assert len(runs) == 1


async def test_production_project_rejects_a_second_active_run(session, integration_settings) -> None:
    project = await make_project(session, integration_settings, kind="production", name="Production Novel")
    service = RunService(session, integration_settings)
    await service.create(project=project, workflow_key="chapter_generation", input_json={"chapter_number": 1})

    with pytest.raises(APIError) as excinfo:
        await service.create(project=project, workflow_key="chapter_generation", input_json={"chapter_number": 2})
    assert excinfo.value.code == "RUN_ALREADY_ACTIVE"
    assert excinfo.value.status_code == 409


# ------------------------------------------------------------------------ artifacts
async def test_artifact_registry_enforces_schema_and_immutability(session, integration_settings) -> None:
    from novel_agent.artifacts.registry import ArtifactDraft
    from novel_agent.artifacts.schemas import ArtifactValidationError

    project = await make_project(session, integration_settings)
    registry = ArtifactRegistry(session, integration_settings)

    with pytest.raises(ArtifactValidationError):
        await registry.create(
            project=project,
            draft=ArtifactDraft(type="scene_brief", content={"scene_id": "1-1"}, producer="scene_planner"),
        )

    valid = {
        "scene_id": "1-2",
        "pov_character_id": "alice",
        "location_id": "black_tower_basement",
        "objective": "找档案",
        "conflict": "有人先来过",
        "required_facts": ["房间没有窗"],
        "forbidden_events": [],
        "tone": ["压抑"],
        "target_words": 1800,
    }
    first = await registry.create(
        project=project, draft=ArtifactDraft(type="scene_brief", content=valid, producer="scene_planner")
    )
    assert first.status == "draft"
    await registry.approve(first.id)
    assert (await registry.get(first.id)).status == "approved"

    second = await registry.create(
        project=project,
        draft=ArtifactDraft(type="scene_brief", content={**valid, "objective": "改写目标"}, producer="scene_planner"),
        parent_id=first.id,
    )
    assert second.parent_id == first.id
    assert (await registry.get(first.id)).status == "superseded"

    with pytest.raises(IllegalStateTransition):
        await registry.approve(first.id)

    lineage = await registry.lineage(second.id)
    assert {"artifact_id": str(first.id), "relation": "derived_from"} in lineage["sources"]
    tree = await registry.lineage_tree(second.id)
    assert tree and tree[0]["artifact_id"] == str(first.id)


async def test_approving_a_canon_patch_moves_artifact_out_of_proposed(session, integration_settings) -> None:
    project = await make_project(session, integration_settings)
    run, _ = await execute_run(session, integration_settings, project)
    registry = ArtifactRegistry(session, integration_settings)
    patch = await registry.latest_for_run(run.id, "canon_patch")
    assert patch is not None
    assert patch.status == "approved"


async def test_style_editor_fact_change_fails_and_preserves_the_draft(session, integration_settings) -> None:
    """§7: the Style Editor may change expression only; facts must not change."""

    project = await make_project(session, integration_settings, name="Style Guard Novel")
    scenario = FakeScenario(style_fact_diff={"added": ["魔法存在"], "removed": [], "changed": []})
    run, _ = await execute_run(session, integration_settings, project, scenario=scenario)

    assert run.status == "failed"
    assert run.error_code == "STYLE_EDITOR_FACT_CHANGE"
    by_key = {node.node_key: node for node in await node_rows(session, run.id)}
    assert by_key["style_editor"].status == "failed"

    # The writer draft is preserved and nothing was committed to chapters/.
    drafts = [artifact for artifact in await artifact_rows(session, run.id) if artifact.type == "chapter_draft"]
    assert len(drafts) == 1
    assert drafts[0].status == "draft"
    style = [artifact for artifact in await artifact_rows(session, run.id) if artifact.type == "style_edit_result"]
    assert style and (style[0].content_json or {})["fact_diff"]["added"] == ["魔法存在"]
    assert not (Path(project.root_path) / "chapters" / "0001" / "final.md").exists()


# -------------------------------------------------------------------- replay
async def test_recorded_replay_reproduces_artifact_hashes(session, integration_settings) -> None:
    project = await make_project(session, integration_settings)
    original, _ = await execute_run(session, integration_settings, project)
    assert original.status == "succeeded"

    original_artifacts = await artifact_rows(session, original.id)
    original_hashes = {artifact.type: artifact.content_hash for artifact in original_artifacts}

    replay_run, _ = await execute_run(
        session,
        integration_settings,
        project,
        mode=MODE_REPLAY_RECORDED,
        input_json={"chapter_number": 1, "replay_of": str(original.id)},
    )
    assert replay_run.status == "succeeded", replay_run.error_message

    replay_artifacts = await artifact_rows(session, replay_run.id)
    replay_hashes = {artifact.type: artifact.content_hash for artifact in replay_artifacts}
    assert replay_hashes == original_hashes

    calls = (await session.execute(select(LlmCall).where(LlmCall.run_id == replay_run.id))).scalars().all()
    providers = {call.model_profile_snapshot.get("provider") for call in calls}
    assert calls and providers == {"recorded"}, providers


# ------------------------------------------------------------------- concurrency
async def test_concurrent_run_creation_on_production_project_is_serialised(
    session, integration_settings
) -> None:
    project = await make_project(session, integration_settings, kind="production", name="Locked Novel")
    service = RunService(session, integration_settings)
    await service.create(project=project, workflow_key="chapter_generation", input_json={"chapter_number": 1})

    results = await asyncio.gather(
        *(
            service.create(project=project, workflow_key="chapter_generation", input_json={"chapter_number": 2})
            for _ in range(3)
        ),
        return_exceptions=True,
    )
    errors = [result for result in results if isinstance(result, APIError)]
    assert errors, "at least one concurrent creation must be rejected"
    assert all(error.code == "RUN_ALREADY_ACTIVE" for error in errors)
    runs = (await session.execute(select(Run).where(Run.project_id == project.id))).scalars().all()
    assert len(runs) == 1


# ------------------------------------------------------------------- diagnostics
async def test_diagnostics_reports_each_dependency(session, engine, integration_settings) -> None:
    from httpx import ASGITransport, AsyncClient
    from redis.asyncio import Redis

    from novel_agent.main import create_app

    app = create_app(integration_settings)
    app.state.db_engine = engine
    redis = Redis.from_url(integration_settings.redis_url, decode_responses=True)
    app.state.redis = redis
    app.state.arq = None
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/diagnostics")
        assert response.status_code == 200
        payload = response.json()
        assert payload["components"]["postgres"]["status"] == "ok"
        assert "artifact_schemas" in payload["components"]
        assert payload["components"]["artifact_schemas"]["details"]["count"] >= 12
        assert "redis" in payload["components"]
    finally:
        await redis.aclose()
