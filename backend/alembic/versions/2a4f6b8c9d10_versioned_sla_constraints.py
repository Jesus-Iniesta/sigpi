"""Allow one SLA version to define every priority.

Revision ID: 2a4f6b8c9d10
Revises: 744530feb03d
"""

from collections.abc import Sequence

from alembic import op

revision: str = "2a4f6b8c9d10"
down_revision: str | Sequence[str] | None = "744530feb03d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_sla_version", "service_level_versions", type_="unique")
    op.create_unique_constraint(
        "uq_sla_version_priority",
        "service_level_versions",
        ["agreement_id", "version", "priority"],
    )
    op.create_check_constraint("ck_sla_version_positive", "service_level_versions", "version > 0")
    op.create_check_constraint(
        "ck_sla_priority_valid",
        "service_level_versions",
        "priority IN ('P1', 'P2', 'P3', 'P4')",
    )
    op.create_check_constraint(
        "ck_sla_first_response_positive",
        "service_level_versions",
        "first_response_minutes > 0",
    )
    op.create_check_constraint(
        "ck_sla_resolution_positive",
        "service_level_versions",
        "resolution_minutes > 0",
    )
    op.create_check_constraint(
        "ck_sla_valid_period",
        "service_level_versions",
        "valid_to IS NULL OR valid_to > valid_from",
    )
    op.create_index(
        "ix_sla_version_lookup",
        "service_level_versions",
        ["agreement_id", "priority", "valid_from"],
    )
    op.create_index(
        "ix_sla_category_active",
        "service_level_agreements",
        ["category_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_sla_category_active", table_name="service_level_agreements")
    op.drop_index("ix_sla_version_lookup", table_name="service_level_versions")
    op.drop_constraint("ck_sla_valid_period", "service_level_versions", type_="check")
    op.drop_constraint("ck_sla_resolution_positive", "service_level_versions", type_="check")
    op.drop_constraint("ck_sla_first_response_positive", "service_level_versions", type_="check")
    op.drop_constraint("ck_sla_priority_valid", "service_level_versions", type_="check")
    op.drop_constraint("ck_sla_version_positive", "service_level_versions", type_="check")
    op.drop_constraint("uq_sla_version_priority", "service_level_versions", type_="unique")
    op.create_unique_constraint(
        "uq_sla_version", "service_level_versions", ["agreement_id", "version"]
    )
