"""Make audit logs append-only."""

from collections.abc import Sequence

from alembic import op

revision: str = "5e1f7a9c3b2d"
down_revision: str | Sequence[str] | None = "4d9e0a2b7c6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_logs_created_at",
        "audit_logs",
        ["created_at"],
    )
    op.create_index(
        "ix_audit_logs_entity_lookup",
        "audit_logs",
        ["entity_type", "entity_id", "created_at"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only; % is not allowed',
                TG_OP
                USING ERRCODE = '55006';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_immutable
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_log_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_immutable ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation()")
    op.drop_index("ix_audit_logs_entity_lookup", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
