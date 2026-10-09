from __future__ import annotations

import httpx
from typer.testing import CliRunner

from novelctl.client import APIClient
from novelctl.main import app


def test_client_uses_api_origin_and_bearer_token(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, headers=kwargs["headers"])
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(httpx, "request", fake_request)
    status, body = APIClient("http://example.test/", "secret").health()
    assert status == 200
    assert body["status"] == "ok"
    assert captured == {
        "method": "GET",
        "url": "http://example.test/api/health",
        "headers": {"Accept": "application/json", "Authorization": "Bearer secret"},
    }


def test_health_command_reads_global_options(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx,
        "request",
        lambda method, url, **kwargs: httpx.Response(200, json={"status": "ok", "service": "api"}),
    )
    result = CliRunner().invoke(app, ["--base-url", "http://example.test", "--json", "health"])
    assert result.exit_code == 0
    assert '"status": "ok"' in result.stdout
