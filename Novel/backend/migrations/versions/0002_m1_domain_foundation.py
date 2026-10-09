"""Add M1 projects, model registry, presets, and action tables.

Revision ID: 0002_m1_domain_foundation
Revises: 0001_enable_pgvector
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0002_m1_domain_foundation"
down_revision: str | None = "0001_enable_pgvector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "presets",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "preset_versions",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("preset_id", _uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_yaml", sa.Text(), nullable=False),
        sa.Column("content_json", _jsonb(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["preset_id"], ["presets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("preset_id", "version", name="uq_preset_versions_preset_version"),
    )
    op.create_table(
        "model_endpoints",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=1024), nullable=False),
        sa.Column("secret_ref", sa.String(length=255), nullable=True),
        sa.Column("capabilities", _jsonb(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "model_profiles",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("endpoint_id", _uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("defaults", _jsonb(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("capabilities", _jsonb(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["endpoint_id"], ["model_endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint_id", "model_name", name="uq_model_profiles_endpoint_model"),
    )
    op.create_table(
        "projects",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default=sa.text("'production'"), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False),
        sa.Column("root_path", sa.String(length=1024), nullable=False),
        sa.Column("active_preset_version_id", _uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('production', 'sandbox')", name="ck_projects_kind"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_projects_status"),
        sa.ForeignKeyConstraint(["active_preset_version_id"], ["preset_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("root_path"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "actions",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("actor_type", sa.String(length=64), server_default=sa.text("'api'"), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("action_type", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=128), nullable=False),
        sa.Column("target_id", _uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_type", "request_id", name="uq_actions_type_request"),
    )
    op.create_index("ix_projects_slug", "projects", ["slug"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_projects_slug", table_name="projects")
    op.drop_table("actions")
    op.drop_table("projects")
    op.drop_table("model_profiles")
    op.drop_table("model_endpoints")
    op.drop_table("preset_versions")
    op.drop_table("presets")
