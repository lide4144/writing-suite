"""Shared fixtures for backend tests.

Unit tests need nothing external. Integration tests (`-m integration`) use a real
PostgreSQL database (`novel_test` by default) so migrations, JSONB, pgvector and
the workflow runtime are exercised against the same engine as production.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlsplit

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from novel_agent.core.config import Settings
from novel_agent.presets.service import ensure_builtin_presets

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://novel:novel-m0-dev-password@127.0.0.1:5432/novel_test"
DEFAULT_TEST_REDIS_URL = "redis://127.0.0.1:6379/15"

DOMAIN_TABLES = (
    "llm_call_context",
    "context_items",
    "llm_calls",
    "artifact_edges",
    "artifacts",
    "events",
    "run_nodes",
    "runs",
    "workflow_definitions",
    "actions",
    "projects",
    "preset_versions",
    "presets",
    "model_profiles",
    "model_endpoints",
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip integration tests when PostgreSQL is unreachable."""

    if os.environ.get("NOVEL_FORCE_INTEGRATION") == "1":
        return
    if _postgres_reachable():
        return
    skip = pytest.mark.skip(reason="integration tests need the native PostgreSQL service")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


def _postgres_reachable() -> bool:
    import socket

    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    parts = urlsplit(url.replace("+asyncpg", ""))
    host = parts.hostname or "127.0.0.1"
    port = parts.port or 5432
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _create_database_if_missing(url: str) -> None:
    """Create the test database with `psql` (keeps this fixture synchronous)."""

    parts = urlsplit(url.replace("+asyncpg", ""))
    database = (parts.path or "/novel_test").lstrip("/")
    user = parts.username or "novel"
    password = parts.password or ""
    host = parts.hostname or "127.0.0.1"
    port = parts.port or 5432
    admin_dsn = f"postgresql://{user}:{password}@{host}:{port}/postgres"

    def psql(*args: str) -> str:
        result = subprocess.run(
            ["psql", admin_dsn, *args], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    exists = psql("-tAc", f"SELECT 1 FROM pg_database WHERE datname = '{database}'")
    if exists != "1":
        psql("-c", f'CREATE DATABASE "{database}"')


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def test_redis_url() -> str:
    return os.environ.get("TEST_REDIS_URL", DEFAULT_TEST_REDIS_URL)


@pytest.fixture(scope="session")
def integration_ready(test_database_url: str) -> bool:
    if not _postgres_reachable():
        pytest.skip("integration tests need the native PostgreSQL service")
    return True


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str, integration_ready: bool) -> str:
    _create_database_if_missing(test_database_url)
    env = {**os.environ, "DATABASE_URL": test_database_url}
    subprocess.run(
        [str(REPO_ROOT / ".venv/bin/alembic"), "-c", "backend/alembic.ini", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [str(REPO_ROOT / ".venv/bin/python"), "-m", "novel_agent.bootstrap"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    return test_database_url


@pytest.fixture(scope="session")
def integration_settings(tmp_path_factory: pytest.TempPathFactory, migrated_database: str, test_redis_url: str) -> Settings:
    projects_root = tmp_path_factory.mktemp("projects")
    return Settings(
        app_env="development",
        app_version="0.1.0-m2-test",
        database_url=migrated_database,
        redis_url=test_redis_url,
        projects_root=str(projects_root),
        presets_root=str(REPO_ROOT / "presets"),
        preset_schema_path=str(REPO_ROOT / "schemas/preset.schema.json"),
        artifact_schemas_root=str(REPO_ROOT / "schemas/artifacts"),
    )


@pytest_asyncio.fixture
async def engine(integration_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(integration_settings.database_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine, integration_settings: Settings):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db_session:
        # Start every test from an empty domain schema and an empty projects root:
        # truncated rows would otherwise leave project directories behind and the
        # next test would hit a slug conflict.
        await db_session.execute(text(f"TRUNCATE {', '.join(DOMAIN_TABLES)} RESTART IDENTITY CASCADE"))
        await db_session.commit()
        projects_root = Path(integration_settings.projects_root)
        if projects_root.is_dir():
            for child in projects_root.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
        await ensure_builtin_presets(db_session, integration_settings)
        await db_session.commit()
        yield db_session
