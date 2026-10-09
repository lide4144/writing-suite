from __future__ import annotations

from novel_agent.db import models  # noqa: F401
from novel_agent.db.base import Base

M1_TABLES = {
    "projects",
    "model_endpoints",
    "model_profiles",
    "presets",
    "preset_versions",
    "actions",
}

M2_TABLES = {
    "workflow_definitions",
    "runs",
    "run_nodes",
    "events",
    "artifacts",
    "artifact_edges",
    "llm_calls",
    "context_items",
    "llm_call_context",
}


def test_m1_foundation_tables_are_registered() -> None:
    assert M1_TABLES <= set(Base.metadata.tables)


def test_m2_runtime_tables_are_registered() -> None:
    assert M2_TABLES <= set(Base.metadata.tables)


def test_metadata_contains_no_undeclared_tables() -> None:
    assert set(Base.metadata.tables) == M1_TABLES | M2_TABLES, (
        "A new table was added without updating this contract test; "
        "keep the declared schema and the migration in sync."
    )
