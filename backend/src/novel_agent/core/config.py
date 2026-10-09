from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_version: str = "0.1.0-m1"
    database_url: str = "postgresql+asyncpg://novel:novel-m0-dev-password@localhost:5432/novel"
    redis_url: str = "redis://localhost:6379/0"
    projects_root: str = "./projects"
    presets_root: str = "./presets"
    preset_schema_path: str = "./schemas/preset.schema.json"
    artifact_schemas_root: str = "./schemas/artifacts"
    artifact_schema_version: str = "1.0"
    context_token_budget: int = 24000
    context_retrieve_top_k: int = 15
    workflow_max_revision_iterations: int = 3
    git_user_name: str = "Novel Agent Platform"
    git_user_email: str = "novel-agent-platform@localhost"
    worker_heartbeat_key: str = "novel:worker:heartbeat"
    worker_heartbeat_ttl_seconds: int = 30
    worker_heartbeat_interval_seconds: int = 5
    worker_id: str = "novel-worker-local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
