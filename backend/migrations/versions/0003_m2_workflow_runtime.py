"""Add M2 artifact registry, workflow runtime, event log and tracing tables.

Revision ID: 0003_m2_workflow_runtime
Revises: 0002_m1_domain_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


revision: str = "0003_m2_workflow_runtime"
down_revision: str | None = "0002_m1_domain_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "workflow_definitions",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("preset_version_id", _uuid(), nullable=True),
        sa.Column("workflow_key", sa.String(length=128), nullable=False),
        sa.Column("dag_json", _jsonb(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["preset_version_id"], ["preset_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_key", "schema_version", name="uq_workflow_definitions_key_schema"),
    )

    op.create_table(
        "runs",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("workflow_key", sa.String(length=128), nullable=False),
        sa.Column("preset_version_id", _uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("mode", sa.String(length=32), server_default=sa.text("'normal'"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("input_json", _jsonb(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("current_node", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'waiting_approval', 'succeeded', 'failed', 'cancelled')",
            name="ck_runs_status",
        ),
        sa.CheckConstraint("mode IN ('normal', 'replay_recorded', 'replay_live')", name="ck_runs_mode"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preset_version_id"], ["preset_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_project_created", "runs", ["project_id", "created_at"], unique=False)
    op.create_index("ix_runs_status", "runs", ["status"], unique=False)

    op.create_table(
        "run_nodes",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("run_id", _uuid(), nullable=False),
        sa.Column("node_key", sa.String(length=128), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("input_artifact_ids", _jsonb(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("output_artifact_ids", _jsonb(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped', 'cancelled')",
            name="ck_run_nodes_status",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "node_key", "attempt", name="uq_run_nodes_run_node_attempt"),
    )
    op.create_index("ix_run_nodes_run", "run_nodes", ["run_id"], unique=False)

    op.create_table(
        "events",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("project_id", _uuid(), nullable=True),
        sa.Column("run_id", _uuid(), nullable=True),
        sa.Column("node_id", _uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=64), server_default=sa.text("'system'"), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", _jsonb(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["run_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sequence"),
    )
    op.create_index("ix_events_run_sequence", "events", ["run_id", "sequence"], unique=False)

    op.create_table(
        "artifacts",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("run_id", _uuid(), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("producer", sa.String(length=64), nullable=False),
        sa.Column("content_json", _jsonb(), nullable=False),
        sa.Column("provenance", _jsonb(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("parent_id", _uuid(), nullable=True),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'proposed', 'approved', 'rejected', 'superseded')",
            name="ck_artifacts_status",
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_artifacts_project_type", "artifacts", ["project_id", "type"], unique=False)
    op.create_index("ix_artifacts_content_hash", "artifacts", ["content_hash"], unique=False)
    op.create_index("ix_artifacts_parent", "artifacts", ["parent_id"], unique=False)

    op.create_table(
        "artifact_edges",
        sa.Column("source_artifact_id", _uuid(), nullable=False),
        sa.Column("target_artifact_id", _uuid(), nullable=False),
        sa.Column("relation", sa.String(length=64), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["source_artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_artifact_id", "target_artifact_id", "relation"),
    )
    op.create_index("ix_artifact_edges_target", "artifact_edges", ["target_artifact_id"], unique=False)

    op.create_table(
        "llm_calls",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("run_id", _uuid(), nullable=True),
        sa.Column("node_id", _uuid(), nullable=True),
        sa.Column("agent_key", sa.String(length=64), nullable=False),
        sa.Column("model_profile_snapshot", _jsonb(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("request_json", _jsonb(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("response_json", _jsonb(), nullable=True),
        sa.Column("usage_json", _jsonb(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(["node_id"], ["run_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_calls_run", "llm_calls", ["run_id"], unique=False)

    op.create_table(
        "context_items",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=512), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata", _jsonb(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_context_items_project_kind", "context_items", ["project_id", "kind"], unique=False)

    op.create_table(
        "llm_call_context",
        sa.Column("llm_call_id", _uuid(), nullable=False),
        sa.Column("context_item_id", _uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["context_item_id"], ["context_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["llm_call_id"], ["llm_calls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("llm_call_id", "context_item_id"),
    )


def downgrade() -> None:
    op.drop_table("llm_call_context")
    op.drop_index("ix_context_items_project_kind", table_name="context_items")
    op.drop_table("context_items")
    op.drop_index("ix_llm_calls_run", table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index("ix_artifact_edges_target", table_name="artifact_edges")
    op.drop_table("artifact_edges")
    op.drop_index("ix_artifacts_parent", table_name="artifacts")
    op.drop_index("ix_artifacts_content_hash", table_name="artifacts")
    op.drop_index("ix_artifacts_project_type", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_events_run_sequence", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_run_nodes_run", table_name="run_nodes")
    op.drop_table("run_nodes")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_project_created", table_name="runs")
    op.drop_table("runs")
    op.drop_table("workflow_definitions")
