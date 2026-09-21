from app.models.enums import Priority

_PRIORITY_MATRIX: dict[tuple[int, int], Priority] = {
    (3, 1): Priority.P2,
    (3, 2): Priority.P1,
    (3, 3): Priority.P1,
    (2, 1): Priority.P3,
    (2, 2): Priority.P2,
    (2, 3): Priority.P1,
    (1, 1): Priority.P4,
    (1, 2): Priority.P3,
    (1, 3): Priority.P2,
}


def _is_level(value: object) -> bool:
    """Accept only real integers from 1 to 3 (bool and float are rejected)."""
    return type(value) is int and 1 <= value <= 3


def calculate_priority(urgency: int, impact: int) -> Priority:
    """Apply RN-05: priority is derived only from urgency and impact."""
    if not (_is_level(urgency) and _is_level(impact)):
        raise ValueError("urgency and impact must be integers from 1 to 3")
    return _PRIORITY_MATRIX[(urgency, impact)]
