"""Add password hash and failed login counter to user accounts (S3-03).

Revision ID: 6f2a8b0d4c1e
Revises: 5e1f7a9c3b2d
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6f2a8b0d4c1e"
down_revision: str | Sequence[str] | None = "5e1f7a9c3b2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("failed_login_attempts", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "password_hash")