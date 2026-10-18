"""Add SLA clock pauses for the «En espera» state (S3-15).

Revision ID: 7a3b9c1d5e2f
Revises: 6f2a8b0d4c1e
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7a3b9c1d5e2f"
down_revision: str | Sequence[str] | None = "6f2a8b0d4c1e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "request_sla_pauses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("started_by_id", sa.Uuid(), nullable=False),
        sa.Column("ended_by_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["service_requests.id"]),
        sa.ForeignKeyConstraint(["started_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ended_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_request_sla_pauses_request_id"), "request_sla_pauses", ["request_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_request_sla_pauses_request_id"), table_name="request_sla_pauses")
    op.drop_table("request_sla_pauses")
