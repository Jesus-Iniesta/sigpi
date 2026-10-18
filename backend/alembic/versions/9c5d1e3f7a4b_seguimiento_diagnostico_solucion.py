"""Add diagnosis, solution and resolution time to service requests.

Revision ID: 9c5d1e3f7a4b
Revises: 8b4c0d2e6f3a
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9c5d1e3f7a4b"
down_revision: str | Sequence[str] | None = "8b4c0d2e6f3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("service_requests", sa.Column("diagnosis", sa.Text(), nullable=True))
    op.add_column("service_requests", sa.Column("solution", sa.Text(), nullable=True))
    op.add_column("service_requests", sa.Column("resolution_minutes", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("service_requests", "resolution_minutes")
    op.drop_column("service_requests", "solution")
    op.drop_column("service_requests", "diagnosis")
