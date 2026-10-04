"""Seed the roles used by identity management.

Revision ID: 4d9e0a2b7c6f
Revises: 3c7e8f1a2b4d
"""

from collections.abc import Sequence
import uuid

import sqlalchemy as sa

from alembic import op

revision: str = "4d9e0a2b7c6f"
down_revision: str | Sequence[str] | None = "3c7e8f1a2b4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_SEEDS = (
    ("administrator", "Control total de la plataforma."),
    ("service_manager", "Gestiona solicitudes, SLA y operación."),
    ("support_agent", "Atiende y actualiza solicitudes asignadas."),
    ("classifier", "Revisa y valida la clasificación de solicitudes."),
    ("knowledge_manager", "Administra el conocimiento institucional."),
    ("auditor", "Consulta información y reportes de auditoría."),
    ("requester", "Crea y consulta sus solicitudes."),
)


def upgrade() -> None:
    roles = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
    )
    existing_names = {
        row[0] for row in op.get_bind().execute(sa.select(roles.c.name)).fetchall()
    }
    op.bulk_insert(
        roles,
        [
            {"id": uuid.uuid4(), "name": name, "description": description}
            for name, description in ROLE_SEEDS
            if name not in existing_names
        ],
    )


def downgrade() -> None:
    roles = sa.table("roles", sa.column("name", sa.String()))
    op.execute(
        roles.delete().where(
            roles.c.name.in_([name for name, _description in ROLE_SEEDS])
        )
    )
