import pytest

from app.domain.priority import calculate_priority
from app.models.enums import Priority


@pytest.mark.parametrize(
    ("urgency", "impact", "expected"),
    [
        (3, 1, Priority.P2),
        (3, 2, Priority.P1),
        (2, 1, Priority.P3),
        (2, 3, Priority.P1),
        (1, 1, Priority.P4),
        (1, 3, Priority.P2),
    ],
)
def test_priority_matrix(urgency: int, impact: int, expected: Priority) -> None:
    assert calculate_priority(urgency, impact) == expected


def test_priority_rejects_values_outside_matrix() -> None:
    with pytest.raises(ValueError):
        calculate_priority(4, 1)
