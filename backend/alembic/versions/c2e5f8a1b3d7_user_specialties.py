"""Create the user_specialties association table (catálogo de técnicos, RN-08).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c2e5f8a1b3d7"
down_revision: str | Sequence[str] | None = "28ce96c0bd74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Por si alguien creó la tabla a mano mientras faltaba la migración.
    if sa.inspect(op.get_bind()).has_table("user_specialties"):
        return
    op.create_table(
        "user_specialties",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("specialty_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["specialty_id"], ["specialties.id"]),
        sa.PrimaryKeyConstraint("user_id", "specialty_id"),
        sa.UniqueConstraint("user_id", "specialty_id", name="uq_user_specialty"),
    )


def downgrade() -> None:
    op.drop_table("user_specialties")