"""Add importance and read marker to notifications (S4-05, HU-07.1).

Revision ID: ad6e2f4b8c5d
Revises: bfbc891766fd
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ad6e2f4b8c5d"
down_revision: str | Sequence[str] | None = "bfbc891766fd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("importance", sa.String(length=10), nullable=False, server_default="normal"),
    )
    op.add_column("notifications", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_notifications_recipient_read", "notifications", ["recipient_id", "read_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_read", table_name="notifications")
    op.drop_column("notifications", "read_at")
    op.drop_column("notifications", "importance")
