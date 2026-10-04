"""Add shift assignment to user accounts.

Revision ID: 3c7e8f1a2b4d
Revises: 2a4f6b8c9d10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3c7e8f1a2b4d"
down_revision: str | Sequence[str] | None = "2a4f6b8c9d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("shift_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_users_shift_id", "users", "shifts", ["shift_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_users_shift_id", "users", type_="foreignkey")
    op.drop_column("users", "shift_id")
