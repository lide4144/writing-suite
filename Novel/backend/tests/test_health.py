from novel_agent.health import assemble_health_response, heartbeat_is_fresh
from novel_agent.main import create_app
from fastapi.testclient import TestClient


def test_healthy_components_produce_http_200() -> None:
    status_code, payload = assemble_health_response(
        {
            "postgres": {"status": "ok"},
            "redis": {"status": "ok"},
            "worker": {"status": "ok"},
        },
        version="test",
    )

    assert status_code == 200
    assert payload["status"] == "ok"
    assert payload["version"] == "test"


def test_stale_or_missing_worker_heartbeat_is_not_fresh() -> None:
    assert not heartbeat_is_fresh(None, now=100, ttl_seconds=30)
    assert not heartbeat_is_fresh('{"timestamp": 60}', now=100, ttl_seconds=30)
    assert heartbeat_is_fresh('{"timestamp": 80}', now=100, ttl_seconds=30)


def test_health_and_compatibility_routes_are_exposed() -> None:
    class FakeChecker:
        async def check(self, app):
            return 200, {
                "status": "ok",
                "service": "api",
                "version": "test",
                "components": {
                    "postgres": {"status": "ok"},
                    "redis": {"status": "ok"},
                    "worker": {"status": "ok"},
                },
            }

    app = create_app()
    app.state.health_checker = FakeChecker()
    with TestClient(app) as client:
        for path in ("/health", "/api/health"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
