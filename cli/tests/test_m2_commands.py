"""M2 command-surface tests for ``novelctl``.

Everything here is offline: ``novelctl.main._client`` is monkeypatched with
:class:`StubAPIClient`, which records every call and replays configured
payloads. No HTTP request, no server and no sleeping is involved.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

import novelctl.main as main_module
from novelctl.client import APIClientError
from novelctl.main import app

RUN_ID = "run-1"
PROJECT = "proj-1"
ARTIFACT_ID = "art-1"

runner = CliRunner()


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if any test reaches httpx instead of the stub."""

    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("these tests must not perform real HTTP requests")

    monkeypatch.setattr("novelctl.client.httpx.request", blocked)
    monkeypatch.setattr("novelctl.client.httpx.stream", blocked)


class StubAPIClient:
    """Drop-in stand-in for ``APIClient`` that never touches the network.

    ``calls`` records ``(method, path, json, idempotency_key)`` tuples in the
    order the CLI made them; ``stream_calls`` records ``(run_id, after)``.
    ``responses`` maps an exact path to either a payload (returned with status
    200) or a ``(status, payload)`` tuple; ``errors`` maps an exact path to the
    exception that should be raised; ``streams`` maps a run id to an iterable of
    ``(sequence, event_type, payload)`` tuples.
    """

    def __init__(
        self,
        responses: dict[str, Any] | None = None,
        streams: dict[str, list[tuple[int, str, dict[str, Any]]]] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.calls: list[tuple[str, str, Any, str | None]] = []
        self.stream_calls: list[tuple[str, int]] = []
        self.responses = dict(responses or {})
        self.streams = dict(streams or {})
        self.errors = dict(errors or {})

    # ------------------------------------------------------------- recording
    @property
    def paths(self) -> list[str]:
        return [path for _, path, _, _ in self.calls]

    def methods_for(self, path: str) -> list[str]:
        return [method for method, candidate, _, _ in self.calls if candidate == path]

    # ------------------------------------------------------------ APIClient
    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        raise_for_status: bool = True,
    ) -> tuple[int, Any]:
        self.calls.append((method, path, json, idempotency_key))
        if path in self.errors:
            raise self.errors[path]
        value = self.responses.get(path, {})
        if isinstance(value, tuple):
            status, body = value
            if raise_for_status and status >= 400:
                raise APIClientError(_error_message(status, body))
            return status, body
        return 200, value

    def get(self, path: str) -> Any:
        return self.request("GET", path)[1]

    def post(self, path: str, payload: dict[str, Any], *, idempotency_key: str | None = None) -> Any:
        return self.request("POST", path, json=payload, idempotency_key=idempotency_key)[1]

    def post_empty(self, path: str, *, idempotency_key: str | None = None) -> Any:
        return self.request("POST", path, idempotency_key=idempotency_key)[1]

    def stream_events(self, run_id: str, *, after: int = 0):
        self.stream_calls.append((run_id, after))
        path = f"/api/v1/runs/{run_id}/events/stream"
        if path in self.errors:
            raise self.errors[path]
        yield from self.streams.get(run_id, ())


def _error_message(status: int, body: Any) -> str:
    """Mirror ``APIClient.request``'s status-to-message mapping."""
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        error = body["error"]
        return f"{error.get('code', 'API_ERROR')}: {error.get('message', 'Request failed')}"
    return f"HTTP {status}: {body}"


def patch_client(monkeypatch: pytest.MonkeyPatch, stub: StubAPIClient) -> StubAPIClient:
    """Route every CLI ``_client()`` lookup (including follow-up calls) to ``stub``."""
    monkeypatch.setattr(main_module, "_client", lambda: stub)
    return stub


def run_cli(*args: str):
    return runner.invoke(app, list(args))


def json_documents(text: str) -> list[Any]:
    """Parse every JSON document in ``text``.

    ``_print`` pretty-prints with an indent while the SSE follower emits compact
    one-line payloads, so a single ``json.loads`` is not enough for ``--json``
    output that mixes both.
    """
    decoder = json.JSONDecoder()
    documents: list[Any] = []
    index = 0
    while True:
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            return documents
        value, index = decoder.raw_decode(text, index)
        documents.append(value)


# ------------------------------------------------------------------- run group


def test_run_status_gets_run_and_prints_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "id": RUN_ID,
        "project_id": PROJECT,
        "status": "running",
        "current_node": "draft_chapter",
        "error_code": None,
    }
    stub = patch_client(monkeypatch, StubAPIClient(responses={f"/api/v1/runs/{RUN_ID}": payload}))

    result = run_cli("run", "status", RUN_ID)

    assert result.exit_code == 0
    assert stub.calls == [("GET", f"/api/v1/runs/{RUN_ID}", None, None)]
    assert f"id: {RUN_ID}" in result.output
    assert "status: running" in result.output
    assert "current_node: draft_chapter" in result.output
    assert "error_code: None" in result.output


def test_run_status_json_round_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"id": RUN_ID, "status": "failed", "error_code": "MODEL_TIMEOUT", "attempt": 2}
    patch_client(monkeypatch, StubAPIClient(responses={f"/api/v1/runs/{RUN_ID}": payload}))

    result = run_cli("--json", "run", "status", RUN_ID)

    assert result.exit_code == 0
    assert json.loads(result.output) == payload


def test_run_chapter_posts_exact_body_and_idempotency_key(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = patch_client(
        monkeypatch,
        StubAPIClient(responses={f"/api/v1/projects/{PROJECT}/runs": {"run_id": RUN_ID, "status": "queued"}}),
    )

    result = run_cli(
        "run",
        "chapter",
        "--project",
        PROJECT,
        "--chapter",
        "3",
        "--idempotency-key",
        "key-123",
    )

    assert result.exit_code == 0
    assert stub.calls == [
        (
            "POST",
            f"/api/v1/projects/{PROJECT}/runs",
            {"workflow": "chapter_generation", "input": {"chapter_number": 3}, "mode": "normal"},
            "key-123",
        )
    ]
    assert f"run_id: {RUN_ID}" in result.output


def test_run_chapter_follow_streams_events_then_fetches_final_status(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        (1, "run.started", {"sequence": 1, "event_type": "run.started", "payload": {"node_key": "plan"}}),
        (
            2,
            "node.completed",
            {"sequence": 2, "event_type": "node.completed", "payload": {"node_key": "draft_chapter"}},
        ),
        (3, "run.completed", {"sequence": 3, "event_type": "run.completed", "payload": {}}),
    ]
    stub = patch_client(
        monkeypatch,
        StubAPIClient(
            responses={
                f"/api/v1/projects/{PROJECT}/runs": {"run_id": RUN_ID, "status": "queued"},
                f"/api/v1/runs/{RUN_ID}": {"id": RUN_ID, "status": "completed", "current_node": None},
            },
            streams={RUN_ID: events},
        ),
    )

    result = run_cli("run", "chapter", "--project", PROJECT, "--chapter", "3", "--follow")

    assert result.exit_code == 0
    assert stub.stream_calls == [(RUN_ID, 0)]
    assert stub.paths == [
        f"/api/v1/projects/{PROJECT}/runs",
        f"/api/v1/runs/{RUN_ID}",
    ]
    output = result.output
    assert f"run_id: {RUN_ID}" in output
    # The run id is printed before any streamed line.
    assert output.index(f"run_id: {RUN_ID}") < output.index("[1] run.started")
    assert "[1] run.started plan" in output
    assert "[2] node.completed draft_chapter" in output
    assert "[3] run.completed" in output
    # Final line comes from the follow-up GET, not from the stream payload.
    assert "status: completed" in output
    assert output.index("[3] run.completed") < output.index("status: completed")


def test_run_chapter_follow_failed_status_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        (1, "run.started", {"sequence": 1, "event_type": "run.started", "payload": {"node_key": "plan"}}),
        (2, "run.failed", {"sequence": 2, "event_type": "run.failed", "payload": {"error_code": "MODEL_TIMEOUT"}}),
    ]
    stub = patch_client(
        monkeypatch,
        StubAPIClient(
            responses={
                f"/api/v1/projects/{PROJECT}/runs": {"run_id": RUN_ID, "status": "queued"},
                f"/api/v1/runs/{RUN_ID}": {"id": RUN_ID, "status": "failed", "error_code": "MODEL_TIMEOUT"},
            },
            streams={RUN_ID: events},
        ),
    )

    result = run_cli("run", "chapter", "--project", PROJECT, "--chapter", "1", "--follow")

    assert result.exit_code == 2
    assert stub.methods_for(f"/api/v1/runs/{RUN_ID}") == ["GET"]
    assert "[2] run.failed" in result.output
    assert "status: failed" in result.output


def test_run_chapter_follow_json_prints_event_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [(1, "run.completed", {"sequence": 1, "event_type": "run.completed", "payload": {"node_key": "final"}})]
    patch_client(
        monkeypatch,
        StubAPIClient(
            responses={
                f"/api/v1/projects/{PROJECT}/runs": {"run_id": RUN_ID, "status": "queued"},
                f"/api/v1/runs/{RUN_ID}": {"id": RUN_ID, "status": "completed"},
            },
            streams={RUN_ID: events},
        ),
    )

    result = run_cli("--json", "run", "chapter", "--project", PROJECT, "--follow")

    assert result.exit_code == 0
    lines = json_documents(result.output)
    assert lines[0] == {"run_id": RUN_ID, "status": "queued"}
    assert lines[1] == {"sequence": 1, "event_type": "run.completed", "payload": {"node_key": "final"}}
    assert lines[-1] == {"id": RUN_ID, "status": "completed"}


def test_run_cancel_posts_to_cancel_endpoint_without_body(monkeypatch: pytest.MonkeyPatch) -> None:
    path = f"/api/v1/runs/{RUN_ID}:cancel"
    stub = patch_client(monkeypatch, StubAPIClient(responses={path: {"id": RUN_ID, "status": "cancelling"}}))

    result = run_cli("run", "cancel", RUN_ID)

    assert result.exit_code == 0
    assert stub.calls == [("POST", path, None, None)]
    assert "status: cancelling" in result.output


def test_run_retry_posts_to_retry_endpoint_without_body(monkeypatch: pytest.MonkeyPatch) -> None:
    path = f"/api/v1/runs/{RUN_ID}:retry"
    stub = patch_client(monkeypatch, StubAPIClient(responses={path: {"id": RUN_ID, "status": "queued"}}))

    result = run_cli("run", "retry", RUN_ID)

    assert result.exit_code == 0
    assert stub.calls == [("POST", path, None, None)]
    assert "status: queued" in result.output


@pytest.mark.parametrize(
    ("argv", "path"),
    [
        (("run", "list", "--project", PROJECT), f"/api/v1/projects/{PROJECT}/runs"),
        (("run", "events", RUN_ID, "--after", "7"), f"/api/v1/runs/{RUN_ID}/events?after=7"),
        (("artifact", "show", ARTIFACT_ID), f"/api/v1/artifacts/{ARTIFACT_ID}"),
        (("artifact", "lineage", ARTIFACT_ID), f"/api/v1/artifacts/{ARTIFACT_ID}/lineage"),
    ],
)
def test_get_style_commands_hit_documented_paths(
    monkeypatch: pytest.MonkeyPatch, argv: tuple[str, ...], path: str
) -> None:
    stub = patch_client(monkeypatch, StubAPIClient(responses={path: {"ok": True}}))

    result = run_cli(*argv)

    assert result.exit_code == 0
    assert stub.calls == [("GET", path, None, None)]


# -------------------------------------------------------------- artifact group


@pytest.mark.parametrize("verb", ["approve", "reject"])
def test_artifact_review_forwards_idempotency_key(monkeypatch: pytest.MonkeyPatch, verb: str) -> None:
    path = f"/api/v1/artifacts/{ARTIFACT_ID}:{verb}"
    stub = patch_client(monkeypatch, StubAPIClient(responses={path: {"artifact_id": ARTIFACT_ID, "status": verb}}))
    key = f"review-{verb}-1"

    result = run_cli("artifact", verb, ARTIFACT_ID, "--idempotency-key", key)

    assert result.exit_code == 0
    assert stub.calls == [("POST", path, None, key)]
    assert f"artifact_id: {ARTIFACT_ID}" in result.output


def test_artifact_list_builds_query_string_with_all_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    path = f"/api/v1/projects/{PROJECT}/artifacts?type=canon_patch&status=proposed&run_id={RUN_ID}"
    stub = patch_client(
        monkeypatch,
        StubAPIClient(responses={path: [{"artifact_id": ARTIFACT_ID, "type": "canon_patch", "status": "proposed"}]}),
    )

    result = run_cli(
        "artifact",
        "list",
        "--project",
        PROJECT,
        "--type",
        "canon_patch",
        "--status",
        "proposed",
        "--run",
        RUN_ID,
    )

    assert result.exit_code == 0
    assert stub.calls == [("GET", path, None, None)]
    assert f"artifact_id={ARTIFACT_ID}" in result.output


def test_artifact_list_two_filters_builds_query_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """The literal M2 command from the spec: only the passed filters appear."""
    path = f"/api/v1/projects/{PROJECT}/artifacts?type=canon_patch&status=proposed"
    stub = patch_client(monkeypatch, StubAPIClient(responses={path: []}))

    result = run_cli("artifact", "list", "--project", PROJECT, "--type", "canon_patch", "--status", "proposed")

    assert result.exit_code == 0
    assert stub.calls == [("GET", path, None, None)]


def test_artifact_list_without_filters_has_no_query_string(monkeypatch: pytest.MonkeyPatch) -> None:
    path = f"/api/v1/projects/{PROJECT}/artifacts"
    stub = patch_client(monkeypatch, StubAPIClient(responses={path: []}))

    result = run_cli("artifact", "list", "--project", PROJECT)

    assert result.exit_code == 0
    assert stub.calls == [("GET", path, None, None)]
    assert "(none)" in result.output


# ------------------------------------------------------------------ debug group


@pytest.mark.parametrize(
    ("argv", "path"),
    [
        (("debug", "errors", RUN_ID), f"/api/v1/debug/runs/{RUN_ID}/errors"),
        (("debug", "trace", RUN_ID), f"/api/v1/debug/runs/{RUN_ID}/trace"),
        (("debug", "context", RUN_ID), f"/api/v1/debug/runs/{RUN_ID}/context"),
        (("debug", "llm-calls", RUN_ID), f"/api/v1/debug/runs/{RUN_ID}/llm-calls"),
    ],
)
def test_debug_commands_hit_documented_paths(
    monkeypatch: pytest.MonkeyPatch, argv: tuple[str, ...], path: str
) -> None:
    stub = patch_client(monkeypatch, StubAPIClient(responses={path: {"run_id": RUN_ID, "detail": "stub"}}))

    result = run_cli(*argv)

    assert result.exit_code == 0
    assert stub.calls == [("GET", path, None, None)]
    assert "detail: stub" in result.output


# ------------------------------------------------------- diagnostics / workflow


def test_diagnostics_prints_components(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {
        "status": "degraded",
        "components": [
            {"name": "postgres", "status": "ok"},
            {"name": "redis", "status": "down"},
        ],
    }
    stub = patch_client(monkeypatch, StubAPIClient(responses={"/api/v1/diagnostics": (200, body)}))

    result = run_cli("diagnostics")

    assert result.exit_code == 0
    assert stub.calls == [("GET", "/api/v1/diagnostics", None, None)]
    assert "status: degraded" in result.output
    assert "postgres" in result.output
    assert "redis" in result.output


def test_diagnostics_5xx_exits_2_and_still_prints_body(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"status": "unavailable", "components": [{"name": "postgres", "status": "down"}]}
    stub = patch_client(monkeypatch, StubAPIClient(responses={"/api/v1/diagnostics": (503, body)}))

    result = run_cli("diagnostics")

    assert result.exit_code == 2
    assert stub.calls == [("GET", "/api/v1/diagnostics", None, None)]
    assert "status: unavailable" in result.output
    assert "postgres" in result.output


def test_workflow_json_prints_dag(monkeypatch: pytest.MonkeyPatch) -> None:
    dag = {
        "key": "chapter_generation",
        "version": 1,
        "nodes": [
            {"node_key": "plan", "type": "llm"},
            {"node_key": "draft_chapter", "type": "llm"},
        ],
        "edges": [{"from": "plan", "to": "draft_chapter"}],
    }
    stub = patch_client(monkeypatch, StubAPIClient(responses={"/api/v1/workflows/chapter_generation": dag}))

    result = run_cli("--json", "workflow", "chapter_generation")

    assert result.exit_code == 0
    assert stub.calls == [("GET", "/api/v1/workflows/chapter_generation", None, None)]
    assert json.loads(result.output) == dag


# ------------------------------------------------------------ failure mapping


@pytest.mark.parametrize(
    ("failure", "expected_exit"),
    [("connection", 3), ("client_error", 2), ("http_500", 2)],
)
def test_failures_map_to_documented_exit_codes(
    monkeypatch: pytest.MonkeyPatch, failure: str, expected_exit: int
) -> None:
    path = f"/api/v1/runs/{RUN_ID}"
    if failure == "connection":
        stub = StubAPIClient(errors={path: APIClientError("boom", connection=True)})
    elif failure == "client_error":
        stub = StubAPIClient(errors={path: APIClientError("boom")})
    else:
        stub = StubAPIClient(responses={path: (500, {"error": {"code": "INTERNAL", "message": "boom"}})})
    patch_client(monkeypatch, stub)

    result = run_cli("run", "status", RUN_ID)

    assert result.exit_code == expected_exit
    assert "boom" in result.output
    assert stub.calls == [("GET", path, None, None)]


def test_connection_failure_during_follow_exits_3(monkeypatch: pytest.MonkeyPatch) -> None:
    stream_path = f"/api/v1/runs/{RUN_ID}/events/stream"
    stub = patch_client(
        monkeypatch,
        StubAPIClient(
            responses={f"/api/v1/projects/{PROJECT}/runs": {"run_id": RUN_ID, "status": "queued"}},
            errors={stream_path: APIClientError("stream lost", connection=True)},
        ),
    )

    result = run_cli("run", "chapter", "--project", PROJECT, "--follow")

    assert result.exit_code == 3
    assert "stream lost" in result.output
    assert stub.stream_calls == [(RUN_ID, 0)]


def test_conflict_error_message_is_surfaced_with_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    path = f"/api/v1/runs/{RUN_ID}:cancel"
    stub = patch_client(
        monkeypatch,
        StubAPIClient(
            responses={path: (409, {"error": {"code": "RUN_NOT_CANCELLABLE", "message": "run already finished"}})}
        ),
    )

    result = run_cli("run", "cancel", RUN_ID)

    assert result.exit_code == 2
    assert "RUN_NOT_CANCELLABLE: run already finished" in result.output
    assert stub.methods_for(path) == ["POST"]
