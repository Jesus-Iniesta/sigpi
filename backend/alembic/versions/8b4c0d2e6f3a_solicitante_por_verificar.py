"""Allow requests without a linked requester (pending verification).

Revision ID: 8b4c0d2e6f3a
Revises: 7a3b9c1d5e2f
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8b4c0d2e6f3a"
down_revision: str | Sequence[str] | None = "7a3b9c1d5e2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "service_requests",
        sa.Column("requester_institutional_id", sa.String(length=80), nullable=True),
    )
    op.create_index(
        op.f("ix_service_requests_requester_institutional_id"),
        "service_requests",
        ["requester_institutional_id"],
        unique=False,
    )
    op.alter_column("service_requests", "requester_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    # Falla si ya existen solicitudes sin solicitante; hay que resolverlas antes de volver atrás.
    op.alter_column("service_requests", "requester_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_index(
        op.f("ix_service_requests_requester_institutional_id"),
        table_name="service_requests",
    )
    op.drop_column("service_requests", "requester_institutional_id")
