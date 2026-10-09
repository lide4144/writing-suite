"""M2 API tests: run creation, SSE, cancel/retry and artifact approval endpoints.

The ARQ pool is replaced by a recording stub so these tests stay deterministic;
the worker itself is exercised in-process through `novel_agent.worker.jobs.execute_run`.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select

from novel_agent.db.models import Artifact, Run
from novel_agent.main import create_app
from novel_agent.worker.jobs import execute_run

pytestmark = pytest.mark.integration


class StubArqPool:
    """Records enqueued jobs instead of talking to Redis."""

    def __init__(self) -> None:
        self.jobs: list[tuple[str, str]] = []

    async def enqueue_job(self, function: str, *args: Any) -> None:
        self.jobs.append((function, str(args[0]) if args else ""))


@pytest_asyncio.fixture
async def api(session, engine, integration_settings):
    app = create_app(integration_settings)
    app.state.db_engine = engine
    redis = Redis.from_url(integration_settings.redis_url, decode_responses=True)
    app.state.redis = redis
    pool = StubArqPool()
    app.state.arq = pool
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, pool, integration_settings
    await redis.aclose()


async def create_project(client: AsyncClient, *, kind: str = "sandbox", name: str = "API Novel") -> dict:
    response = await client.post("/api/v1/projects", json={"name": name, "kind": kind})
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_run_returns_202_with_links_and_enqueues(api) -> None:
    client, pool, _ = api
    project = await create_project(client)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "chapter_generation", "input": {"chapter_number": 1}, "mode": "normal"},
        headers={"Idempotency-Key": "api-run-1"},
    )
    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["links"]["self"] == f"/api/v1/runs/{payload['run_id']}"
    assert payload["links"]["stream"].endswith("/events/stream")
    assert pool.jobs == [("execute_run", payload["run_id"])]

    # Replaying the same Idempotency-Key reuses the run instead of creating one.
    replay = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "chapter_generation", "input": {"chapter_number": 1}, "mode": "normal"},
        headers={"Idempotency-Key": "api-run-1"},
    )
    assert replay.status_code == 202
    assert replay.json()["run_id"] == payload["run_id"]


async def test_full_api_flow_with_in_process_worker(api, engine) -> None:
    client, pool, settings = api
    project = await create_project(client)
    created = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "chapter_generation", "input": {"chapter_number": 1}},
        headers={"Idempotency-Key": "api-run-flow"},
    )
    run_id = created.json()["run_id"]

    result = await execute_run({"db_engine": engine, "settings": settings}, run_id)
    assert result["status"] == "succeeded", result

    run = (await client.get(f"/api/v1/runs/{run_id}")).json()
    assert run["status"] == "succeeded"
    assert run["current_node"] == "canon_manager"

    nodes = (await client.get(f"/api/v1/runs/{run_id}/nodes")).json()
    assert {node["node_key"] for node in nodes} >= {"director", "writer", "quality_gate", "canon_manager"}

    artifacts = (await client.get(f"/api/v1/projects/{project['id']}/artifacts")).json()
    assert len(artifacts) >= 11
    artifact_id = artifacts[0]["artifact_id"]
    single = (await client.get(f"/api/v1/artifacts/{artifact_id}")).json()
    assert single["content_hash"] == artifacts[0]["content_hash"]

    lineage = (await client.get(f"/api/v1/artifacts/{artifact_id}/lineage")).json()
    assert {"sources", "targets", "ancestors"} <= set(lineage)

    trace = (await client.get(f"/api/v1/debug/runs/{run_id}/trace")).json()
    assert trace["run"]["status"] == "succeeded"
    assert trace["nodes"] and trace["artifacts"] and trace["llm_calls"]
    assert trace["errors"] == []

    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    assert events["last_sequence"] > 0
    assert {"run.queued", "run.completed"} <= {event["event_type"] for event in events["events"]}

    assert (await client.get(f"/api/v1/debug/runs/{run_id}/context")).json()
    workflow = (await client.get("/api/v1/workflows/chapter_generation")).json()
    assert workflow["workflow_key"] == "chapter_generation"
    assert workflow["nodes"]


async def test_sse_stream_replays_events_and_terminates(api, engine) -> None:
    client, _, settings = api
    project = await create_project(client, name="SSE Novel")
    created = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "chapter_generation", "input": {"chapter_number": 1}},
    )
    run_id = created.json()["run_id"]
    await execute_run({"db_engine": engine, "settings": settings}, run_id)

    received: list[str] = []
    async with client.stream("GET", f"/api/v1/runs/{run_id}/events/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                received.append(line.removeprefix("event: "))
            if len(received) > 3 and received[-1] == "run.completed":
                break

    assert "run.queued" in received
    assert "run.completed" in received
    assert received[-1] == "run.completed"


async def test_sse_stream_resumes_from_last_event_id(api, engine) -> None:
    client, _, settings = api
    project = await create_project(client, name="SSE Resume Novel")
    created = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "chapter_generation", "input": {"chapter_number": 1}},
    )
    run_id = created.json()["run_id"]
    await execute_run({"db_engine": engine, "settings": settings}, run_id)

    first_batch = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    midpoint = first_batch["events"][len(first_batch["events"]) // 2]["sequence"]

    received: list[int] = []
    async with client.stream(
        "GET",
        f"/api/v1/runs/{run_id}/events/stream",
        headers={"Last-Event-ID": str(midpoint)},
    ) as response:
        async for line in response.aiter_lines():
            if line.startswith("id: "):
                received.append(int(line.removeprefix("id: ")))
            if received and received[-1] == first_batch["last_sequence"]:
                break

    assert received, "resumed stream must emit the remaining events"
    assert min(received) > midpoint


async def test_cancel_and_retry_endpoints(api, engine) -> None:
    client, pool, settings = api
    project = await create_project(client, name="Cancel Novel")
    created = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "chapter_generation", "input": {"chapter_number": 1}},
    )
    run_id = created.json()["run_id"]

    cancelled = await client.post(f"/api/v1/runs/{run_id}:cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # A cancelled run is terminal, so :retry starts a new attempt that points
    # back at the original run instead of mutating history.
    retried = await client.post(f"/api/v1/runs/{run_id}:retry")
    assert retried.status_code == 202
    retry_run_id = retried.json()["run_id"]
    assert retry_run_id != run_id
    assert retried.json()["status"] == "queued"
    assert pool.jobs[-1] == ("execute_run", retry_run_id)

    original = (await client.get(f"/api/v1/runs/{run_id}")).json()
    assert original["status"] == "cancelled"
    retried_run = (await client.get(f"/api/v1/runs/{retry_run_id}")).json()
    assert retried_run["input"]["retry_of"] == run_id

    result = await execute_run({"db_engine": engine, "settings": settings}, retry_run_id)
    assert result["status"] == "succeeded", result


async def test_approving_a_canon_patch_resumes_a_waiting_run(api, engine, session) -> None:
    client, pool, settings = api
    # Production projects never auto-approve: the run parks at canon_approval.
    project = await create_project(client, kind="production", name="Approval Novel")
    created = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "chapter_generation", "input": {"chapter_number": 1}},
    )
    run_id = created.json()["run_id"]
    result = await execute_run({"db_engine": engine, "settings": settings}, run_id)
    assert result["status"] == "waiting_approval", result

    run = (await client.get(f"/api/v1/runs/{run_id}")).json()
    assert run["status"] == "waiting_approval"
    assert run["current_node"] == "canon_approval"

    patch = (
        await session.execute(
            select(Artifact).where(Artifact.run_id == run_id, Artifact.type == "canon_patch")
        )
    ).scalars().first()
    assert patch is not None
    assert patch.status == "proposed"

    approved = await client.post(f"/api/v1/artifacts/{patch.id}:approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    resumed = (await client.get(f"/api/v1/runs/{run_id}")).json()
    assert resumed["status"] in {"running", "queued"}
    assert pool.jobs[-1] == ("execute_run", run_id), "approval must re-enqueue the run"

    result = await execute_run({"db_engine": engine, "settings": settings}, run_id)
    assert result["status"] == "succeeded", result
    final = (await client.get(f"/api/v1/runs/{run_id}")).json()
    assert final["status"] == "succeeded"


async def test_rejecting_a_canon_patch_keeps_the_draft(api, engine, session) -> None:
    client, _, settings = api
    project = await create_project(client, kind="production", name="Reject Novel")
    created = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "chapter_generation", "input": {"chapter_number": 1}},
    )
    run_id = created.json()["run_id"]
    result = await execute_run({"db_engine": engine, "settings": settings}, run_id)
    assert result["status"] == "waiting_approval", result

    patch = (
        await session.execute(
            select(Artifact).where(Artifact.run_id == run_id, Artifact.type == "canon_patch")
        )
    ).scalars().first()
    assert patch is not None
    assert patch.status == "proposed"

    rejected = await client.post(f"/api/v1/artifacts/{patch.id}:reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    result = await execute_run({"db_engine": engine, "settings": settings}, run_id)
    assert result["status"] == "succeeded", result
    nodes = (await client.get(f"/api/v1/runs/{run_id}/nodes")).json()
    by_key: dict[str, list[dict]] = {}
    for node in nodes:
        by_key.setdefault(node["node_key"], []).append(node)
    assert [node["status"] for node in by_key["keep_draft"]] == ["succeeded"]
    assert all(node["status"] == "skipped" for node in by_key["canon_manager"])


async def test_run_input_validation_and_unknown_workflow(api) -> None:
    client, _, _ = api
    project = await create_project(client, name="Validation Novel")

    bad_chapter = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "chapter_generation", "input": {"chapter_number": 0}},
    )
    assert bad_chapter.status_code == 422
    assert bad_chapter.json()["error"]["code"] == "RUN_INPUT_INVALID"

    unknown = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "nope", "input": {}},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "WORKFLOW_NOT_FOUND"

    missing_project = await client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/runs",
        json={"workflow": "chapter_generation", "input": {}},
    )
    assert missing_project.status_code == 404
    assert missing_project.json()["error"]["code"] == "PROJECT_NOT_FOUND"


async def test_second_active_run_on_production_project_is_rejected_over_http(api) -> None:
    client, _, _ = api
    project = await create_project(client, kind="production", name="Production HTTP Novel")
    first = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "chapter_generation", "input": {"chapter_number": 1}},
    )
    assert first.status_code == 202

    second = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "chapter_generation", "input": {"chapter_number": 2}},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "RUN_ALREADY_ACTIVE"
    assert second.json()["error"]["request_id"]


async def test_runs_are_listed_for_the_project(api, engine) -> None:
    client, _, settings = api
    project = await create_project(client, name="List Novel")
    created = await client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"workflow": "chapter_generation", "input": {"chapter_number": 1}},
    )
    await execute_run({"db_engine": engine, "settings": settings}, created.json()["run_id"])

    listing = (await client.get(f"/api/v1/projects/{project['id']}/runs")).json()
    assert len(listing) == 1
    assert listing[0]["id"] == created.json()["run_id"]
    assert listing[0]["status"] == "succeeded"
