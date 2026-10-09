from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import click
import typer

from novelctl.client import APIClient, APIClientError

app = typer.Typer(help="Novel Agent Platform API client.", no_args_is_help=True)
project_app = typer.Typer(help="Manage projects.", no_args_is_help=True)
preset_app = typer.Typer(help="Manage presets.", no_args_is_help=True)
run_app = typer.Typer(help="Start and inspect workflow runs.", no_args_is_help=True)
artifact_app = typer.Typer(help="Inspect and review artifacts.", no_args_is_help=True)
debug_app = typer.Typer(help="Debug traces for a run.", no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(preset_app, name="preset")
app.add_typer(run_app, name="run")
app.add_typer(artifact_app, name="artifact")
app.add_typer(debug_app, name="debug")


def _config_path() -> Path:
    base = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "novelctl" / "config.json"


def _load_config() -> dict[str, Any]:
    try:
        value = json.loads(_config_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _state() -> dict[str, Any]:
    context = click.get_current_context()
    return context.ensure_object(dict)


def _client() -> APIClient:
    state = _state()
    config = _load_config()
    base_url = state.get("base_url") or os.getenv("NOVEL_API_URL") or config.get("base_url") or "http://127.0.0.1"
    token = state.get("token") or os.getenv("NOVEL_API_TOKEN") or config.get("token")
    return APIClient(str(base_url), str(token) if token else None)


def _row_keys(item: dict[str, Any]) -> list[str]:
    preferred = (
        "id",
        "artifact_id",
        "run_id",
        "node_key",
        "type",
        "name",
        "slug",
        "status",
        "current_node",
        "sequence",
        "event_type",
    )
    return [key for key in preferred if key in item][:6]


def _print(value: Any) -> None:
    if _state().get("json_output"):
        typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))
        return
    if isinstance(value, list):
        if not value:
            typer.echo("(none)")
            return
        for item in value:
            if isinstance(item, dict):
                keys = _row_keys(item)
                typer.echo("\t".join(f"{key}={item.get(key, '')}" for key in keys))
            else:
                typer.echo(str(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                typer.echo(f"{key}: {json.dumps(item, ensure_ascii=False, default=str)}")
            else:
                typer.echo(f"{key}: {item}")
    else:
        typer.echo(str(value))


def _invoke(call):
    try:
        return call()
    except APIClientError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3 if exc.connection else 2) from exc


@app.callback()
def root_options(
    ctx: typer.Context,
    base_url: str | None = typer.Option(None, "--base-url", help="API origin, for example http://127.0.0.1:18080."),
    token: str | None = typer.Option(None, "--token", help="Bearer token; it is never printed."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    ctx.ensure_object(dict)
    ctx.obj.update({"base_url": base_url, "token": token, "json_output": json_output})


@app.command()
def health() -> None:
    """Check API, database, Redis, and worker health."""
    status, body = _invoke(lambda: _client().health())
    _print(body)
    if status >= 400:
        raise typer.Exit(code=2)


@project_app.command("create")
def project_create(
    name: str = typer.Option(..., "--name", help="Project display name."),
    slug: str | None = typer.Option(None, "--slug"),
    kind: str = typer.Option("production", "--kind", case_sensitive=False),
    preset_version_id: str | None = typer.Option(None, "--preset-version-id"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    payload: dict[str, Any] = {"name": name, "kind": kind}
    if slug:
        payload["slug"] = slug
    if preset_version_id:
        payload["active_preset_version_id"] = preset_version_id
    result = _invoke(lambda: _client().post("/api/v1/projects", payload, idempotency_key=idempotency_key))
    _print(result)


@project_app.command("list")
def project_list() -> None:
    """List projects."""
    _print(_invoke(lambda: _client().get("/api/v1/projects")))


@preset_app.command("list")
def preset_list() -> None:
    """List presets and their latest versions."""
    _print(_invoke(lambda: _client().get("/api/v1/presets")))


@preset_app.command("apply")
def preset_apply(
    preset_ref: str = typer.Argument(..., help="Preset name, UUID, or name:version."),
    project: str = typer.Option(..., "--project", help="Project UUID."),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    version_number: int | None = None
    preset_name = preset_ref
    if ":" in preset_ref:
        candidate_name, candidate_version = preset_ref.rsplit(":", 1)
        if candidate_version.isdigit():
            preset_name = candidate_name
            version_number = int(candidate_version)

    def resolve_and_apply() -> Any:
        client = _client()
        presets = client.get("/api/v1/presets")
        selected = next((item for item in presets if item.get("id") == preset_name or item.get("name") == preset_name), None)
        if selected is None:
            raise APIClientError(f"Preset not found: {preset_name}")
        latest = selected.get("latest_version") or {}
        if version_number is None:
            version_id = latest.get("id")
        else:
            version_id = client.get(
                f"/api/v1/presets/{selected['id']}/versions/{version_number}"
            ).get("id")
        if not version_id:
            raise APIClientError("The selected preset has no version.")
        return client.post(
            f"/api/v1/projects/{project}/preset:apply",
            {"preset_version_id": version_id},
            idempotency_key=idempotency_key,
        )

    _print(_invoke(resolve_and_apply))


# ------------------------------------------------------------------------ runs


@run_app.command("chapter")
def run_chapter(
    project: str = typer.Option(..., "--project", help="Project UUID."),
    chapter: int = typer.Option(1, "--chapter", min=1, help="Chapter number to generate."),
    workflow: str = typer.Option("chapter_generation", "--workflow"),
    mode: str = typer.Option("normal", "--mode", help="normal | replay_recorded | replay_live."),
    follow: bool = typer.Option(False, "--follow", help="Consume the SSE stream until the run ends."),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    """Start a chapter generation run and optionally follow its events."""
    result = _invoke(
        lambda: _client().post(
            f"/api/v1/projects/{project}/runs",
            {"workflow": workflow, "input": {"chapter_number": chapter}, "mode": mode},
            idempotency_key=idempotency_key,
        )
    )
    _print(result)
    if follow:
        _follow_run(str(result.get("run_id")))


def _follow_run(run_id: str) -> None:
    client = _client()
    json_output = bool(_state().get("json_output"))
    last_sequence = 0

    def consume() -> None:
        nonlocal last_sequence
        for sequence, event_type, payload in client.stream_events(run_id, after=last_sequence):
            last_sequence = sequence
            if json_output:
                typer.echo(json.dumps(payload, ensure_ascii=False, default=str))
            else:
                detail = payload.get("payload") or {}
                node_key = detail.get("node_key") or ""
                extra = detail.get("artifact_type") or detail.get("decision") or detail.get("error_code") or ""
                typer.echo(f"[{sequence}] {event_type} {node_key} {extra}".rstrip())
            if event_type in {"run.completed", "run.failed", "run.cancelled", "run.waiting_approval"}:
                return

    _invoke(consume)
    final = _invoke(lambda: client.get(f"/api/v1/runs/{run_id}"))
    _print(final)
    if final.get("status") == "failed":
        raise typer.Exit(code=2)


@run_app.command("list")
def run_list(project: str = typer.Option(..., "--project", help="Project UUID.")) -> None:
    """List runs of a project, newest first."""
    _print(_invoke(lambda: _client().get(f"/api/v1/projects/{project}/runs")))


@run_app.command("status")
def run_status(run_id: str = typer.Argument(...)) -> None:
    """Show one run, including its current node and error code."""
    _print(_invoke(lambda: _client().get(f"/api/v1/runs/{run_id}")))


@run_app.command("events")
def run_events(
    run_id: str = typer.Argument(...),
    after: int = typer.Option(0, "--after", min=0, help="First sequence to return."),
) -> None:
    """Print the persisted event log for a run."""
    _print(_invoke(lambda: _client().get(f"/api/v1/runs/{run_id}/events?after={after}")))


@run_app.command("cancel")
def run_cancel(run_id: str = typer.Argument(...)) -> None:
    """Request cancellation; in-flight nodes are cancelled by the worker."""
    _print(_invoke(lambda: _client().post_empty(f"/api/v1/runs/{run_id}:cancel")))


@run_app.command("retry")
def run_retry(run_id: str = typer.Argument(...)) -> None:
    """Resume a waiting run, or start a new attempt for a failed/cancelled run."""
    _print(_invoke(lambda: _client().post_empty(f"/api/v1/runs/{run_id}:retry")))


# ------------------------------------------------------------------- artifacts


@artifact_app.command("list")
def artifact_list(
    project: str = typer.Option(..., "--project", help="Project UUID."),
    type: str | None = typer.Option(None, "--type", help="Filter by artifact type."),
    status: str | None = typer.Option(None, "--status"),
    run_id: str | None = typer.Option(None, "--run"),
) -> None:
    """List artifacts of a project."""
    filters = {
        key: value
        for key, value in (("type", type), ("status", status), ("run_id", run_id))
        if value
    }
    query = urlencode(filters)
    path = f"/api/v1/projects/{project}/artifacts" + (f"?{query}" if query else "")
    _print(_invoke(lambda: _client().get(path)))


@artifact_app.command("show")
def artifact_show(artifact_id: str = typer.Argument(...)) -> None:
    """Show one artifact envelope, content and hash."""
    _print(_invoke(lambda: _client().get(f"/api/v1/artifacts/{artifact_id}")))


@artifact_app.command("lineage")
def artifact_lineage(artifact_id: str = typer.Argument(...)) -> None:
    """Show the lineage (sources, targets, ancestors) of an artifact."""
    _print(_invoke(lambda: _client().get(f"/api/v1/artifacts/{artifact_id}/lineage")))


@artifact_app.command("approve")
def artifact_approve(
    artifact_id: str = typer.Argument(...),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    """Approve a proposed artifact (for a canon patch this resumes its run)."""
    _print(
        _invoke(
            lambda: _client().post_empty(f"/api/v1/artifacts/{artifact_id}:approve", idempotency_key=idempotency_key)
        )
    )


@artifact_app.command("reject")
def artifact_reject(
    artifact_id: str = typer.Argument(...),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    """Reject a proposed artifact; its run keeps the draft for human editing."""
    _print(
        _invoke(
            lambda: _client().post_empty(f"/api/v1/artifacts/{artifact_id}:reject", idempotency_key=idempotency_key)
        )
    )


# ----------------------------------------------------------------------- debug


@debug_app.command("trace")
def debug_trace(run_id: str = typer.Argument(...)) -> None:
    """Print the full trace: run, nodes, artifacts, events and LLM calls."""
    _print(_invoke(lambda: _client().get(f"/api/v1/debug/runs/{run_id}/trace")))


@debug_app.command("errors")
def debug_errors(run_id: str = typer.Argument(...)) -> None:
    """Print only the errors of a run (run, node and LLM call level)."""
    _print(_invoke(lambda: _client().get(f"/api/v1/debug/runs/{run_id}/errors")))


@debug_app.command("llm-calls")
def debug_llm_calls(run_id: str = typer.Argument(...)) -> None:
    """Print recorded LLM calls, including redacted prompts and usage."""
    _print(_invoke(lambda: _client().get(f"/api/v1/debug/runs/{run_id}/llm-calls")))


@debug_app.command("context")
def debug_context(run_id: str = typer.Argument(...)) -> None:
    """Print the context each LLM call actually received."""
    _print(_invoke(lambda: _client().get(f"/api/v1/debug/runs/{run_id}/context")))


@app.command()
def diagnostics() -> None:
    """Explain dependency health: PostgreSQL, Redis, worker, filesystem, Git, schemas."""
    status, body = _invoke(lambda: _client().request("GET", "/api/v1/diagnostics", raise_for_status=False))
    _print(body)
    if status >= 400:
        raise typer.Exit(code=2)


@app.command()
def workflow(workflow_key: str = typer.Argument("chapter_generation")) -> None:
    """Print the read-only DAG of a workflow."""
    _print(_invoke(lambda: _client().get(f"/api/v1/workflows/{workflow_key}")))


if __name__ == "__main__":
    app()
