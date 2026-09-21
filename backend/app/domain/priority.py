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


def calculate_priority(urgency: int, impact: int) -> Priority:
    """Apply RN-05: priority is derived only from urgency and impact."""
    try:
        return _PRIORITY_MATRIX[(urgency, impact)]
    except KeyError as exc:
        raise ValueError("urgency and impact must be integers from 1 to 3") from exc
