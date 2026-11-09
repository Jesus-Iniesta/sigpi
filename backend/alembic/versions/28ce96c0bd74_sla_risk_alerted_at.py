"""Add the SLA risk alert marker to service requests (S4-08, HU-07.2).

Revision ID: 28ce96c0bd74
Revises: ad6e2f4b8c5d
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "28ce96c0bd74"
down_revision: str | Sequence[str] | None = "ad6e2f4b8c5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "service_requests",
        sa.Column("sla_risk_alerted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("service_requests", "sla_risk_alerted_at")
