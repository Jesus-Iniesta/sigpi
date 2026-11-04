"""Bloquea TRUNCATE sobre audit_logs (COR-03, S2-09).

El trigger `audit_logs_immutable` de la migración 5e1f7a9c3b2d es `FOR EACH ROW` y solo
cubre UPDATE y DELETE; un `TRUNCATE audit_logs` borraba todo sin error. Este trigger de
sentencia reutiliza la misma función `prevent_audit_log_mutation()`.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "bfbc891766fd"
down_revision: str | Sequence[str] | None = "9c5d1e3f7a4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TRIGGER audit_logs_block_truncate
        BEFORE TRUNCATE ON audit_logs
        FOR EACH STATEMENT
        EXECUTE FUNCTION prevent_audit_log_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_block_truncate ON audit_logs")
