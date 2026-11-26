"""Ajustes en caliente y modelos reentrenados del clasificador (S5-06, HU-12.1, HU-12.2).

Revision ID: d3f6a9b2c4e8
Revises: c2e5f8a1b3d7
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d3f6a9b2c4e8"
down_revision: str | Sequence[str] | None = "c2e5f8a1b3d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "classifier_models",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version", sa.String(length=60), nullable=False, unique=True),
        sa.Column("accuracy", sa.Numeric(5, 4), nullable=False),
        sa.Column("examples", sa.Integer(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_classifier_models_is_active", "classifier_models", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_classifier_models_is_active", table_name="classifier_models")
    op.drop_table("classifier_models")
    op.drop_table("app_settings")
