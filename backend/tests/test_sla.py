from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models.sla import ServiceLevelVersion


def test_sla_versions_are_unique_per_priority() -> None:
    constraints = ServiceLevelVersion.__table__.constraints

    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_sla_version_priority"
        and {column.name for column in constraint.columns}
        == {"agreement_id", "version", "priority"}
        for constraint in constraints
    )


def test_sla_versions_validate_priority_and_time_values() -> None:
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in ServiceLevelVersion.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_sla_priority_valid" in checks
    assert "ck_sla_first_response_positive" in checks
    assert "ck_sla_resolution_positive" in checks
    assert "ck_sla_valid_period" in checks
