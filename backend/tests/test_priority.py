import pytest

from app.domain.priority import calculate_priority
from app.models.enums import Priority

# RN-05 (Modelado de Negocios, tabla 32). Filas: urgencia; columnas: impacto 1, 2 y 3.
RN_05: dict[int, tuple[Priority, Priority, Priority]] = {
    3: (Priority.P2, Priority.P1, Priority.P1),
    2: (Priority.P3, Priority.P2, Priority.P1),
    1: (Priority.P4, Priority.P3, Priority.P2),
}
CASES = [(u, i, RN_05[u][i - 1]) for u in RN_05 for i in (1, 2, 3)]
RANK = {Priority.P1: 1, Priority.P2: 2, Priority.P3: 3, Priority.P4: 4}


def test_rn05_table_has_nine_combinations() -> None:
    assert len(CASES) == 9


@pytest.mark.parametrize(
    ("urgency", "impact", "expected"),
    CASES,
    ids=[f"urgency{u}-impact{i}" for u, i, _ in CASES],
)
def test_priority_matrix(urgency: int, impact: int, expected: Priority) -> None:
    assert calculate_priority(urgency, impact) == expected


def test_priority_never_drops_when_urgency_or_impact_grows() -> None:
    for urgency in (1, 2, 3):
        for impact in (1, 2, 3):
            current = RANK[calculate_priority(urgency, impact)]
            if urgency < 3:
                assert RANK[calculate_priority(urgency + 1, impact)] <= current
            if impact < 3:
                assert RANK[calculate_priority(urgency, impact + 1)] <= current


@pytest.mark.parametrize(
    ("urgency", "impact"),
    [(0, 1), (4, 1), (1, 0), (1, 4), (-1, 2), (None, 1), ("2", 1), (2.0, 1), (True, 1), (1, False)],
)
def test_priority_rejects_values_outside_matrix(urgency: object, impact: object) -> None:
    with pytest.raises(ValueError):
        calculate_priority(urgency, impact)  # type: ignore[arg-type]
