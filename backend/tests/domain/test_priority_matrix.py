"""Pruebas de la matriz de prioridad RN-05 y el intento de edición directa (S3-07, HU-02.3).

La matriz de prioridad deriva el nivel P1–P4 a partir de la urgencia y el impacto,
ambos enteros de 1 a 3. La prioridad es un campo derivado: no se puede escribir
ni editar directamente desde el cliente ni desde el servicio.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.domain.priority import calculate_priority
from app.models.enums import Priority
from app.schemas.request import RequestAssistedCreate, RequestCreate, RequestUpdate

# RN-05 (Modelado de Negocios, tabla 32). Filas: urgencia; columnas: impacto 1, 2 y 3.
RN_05: dict[int, tuple[Priority, Priority, Priority]] = {
    3: (Priority.P2, Priority.P1, Priority.P1),
    2: (Priority.P3, Priority.P2, Priority.P1),
    1: (Priority.P4, Priority.P3, Priority.P2),
}
CASES = [(u, i, RN_05[u][i - 1]) for u in sorted(RN_05, reverse=True) for i in (1, 2, 3)]
RANK = {Priority.P1: 1, Priority.P2: 2, Priority.P3: 3, Priority.P4: 4}


# --- AC1: las nueve combinaciones de la matriz -------------------------------


def test_matriz_tiene_exactamente_nueve_combinaciones() -> None:
    assert len(CASES) == 9


@pytest.mark.parametrize(
    ("urgency", "impact", "expected"),
    CASES,
    ids=[f"urgency{u}-impact{i}" for u, i, _ in CASES],
)
def test_cada_combinacion_devuelve_la_prioridad_esperada(
    urgency: int, impact: int, expected: Priority
) -> None:
    assert calculate_priority(urgency, impact) is expected


def test_prioridad_es_monotonica_al_crecer_urgencia_o_impacto() -> None:
    """Aumentar urgencia o impacto nunca empeora la prioridad (P4 → P3 → P2 → P1)."""
    for urgency in (1, 2, 3):
        for impact in (1, 2, 3):
            current = RANK[calculate_priority(urgency, impact)]
            if urgency < 3:
                assert RANK[calculate_priority(urgency + 1, impact)] <= current
            if impact < 3:
                assert RANK[calculate_priority(urgency, impact + 1)] <= current


def test_combinacion_maxima_es_p1() -> None:
    """Urgencia 3 + impacto 3 es la combinación más crítica: siempre P1."""
    assert calculate_priority(3, 3) is Priority.P1


def test_combinacion_minima_es_p4() -> None:
    """Urgencia 1 + impacto 1 es la combinación menos crítica: siempre P4."""
    assert calculate_priority(1, 1) is Priority.P4


def test_calcular_prioridad_es_deterministico() -> None:
    """Las mismas entradas siempre producen la misma salida."""
    for urgency in (1, 2, 3):
        for impact in (1, 2, 3):
            assert calculate_priority(urgency, impact) is calculate_priority(
                urgency, impact
            )


# --- AC2: intento de edición directa -----------------------------------------


@pytest.mark.parametrize(
    ("urgency", "impact"),
    [(0, 1), (4, 1), (1, 0), (1, 4), (-1, 2), (None, 1), ("2", 1), (2.0, 1), (True, 1), (1, False)],
)
def test_calculate_priority_rechaza_valores_invalidos(
    urgency: object, impact: object
) -> None:
    with pytest.raises(ValueError, match="urgency and impact must be integers"):
        calculate_priority(urgency, impact)  # type: ignore[arg-type]


def _minimal_request_create(**overrides) -> dict:
    payload = {
        "requester_id": uuid.uuid4(),
        "title": "No hay conexión",
        "description": "El laboratorio perdió conectividad.",
        "physical_location": "Edificio A, laboratorio 2",
    }
    payload.update(overrides)
    return payload


def test_request_create_rechaza_campo_priority_directo() -> None:
    """Intento de edición directa: priority no es un campo escribible al crear."""
    with pytest.raises(ValidationError, match="priority"):
        RequestCreate(**_minimal_request_create(priority=Priority.P1))


def test_request_update_rechaza_campo_priority_directo() -> None:
    """Intento de edición directa: priority no es un campo editable."""
    extra_field: dict = {"priority": Priority.P1}
    with pytest.raises(ValidationError, match="priority"):
        RequestUpdate(**extra_field)


def test_request_assisted_create_rechaza_campo_priority_directo() -> None:
    """Intento de edición directa: el registro asistido tampoco acepta priority."""
    with pytest.raises(ValidationError, match="priority"):
        RequestAssistedCreate(
            **_minimal_request_create(channel="phone", priority=Priority.P1)
        )


def test_request_create_permite_urgencia_e_impacto_pero_no_priority() -> None:
    """El cliente envía urgencia e impacto; la prioridad se deriva, no se envía."""
    request = RequestCreate(
        **_minimal_request_create(urgency=3, impact=2)
    )

    assert request.urgency == 3
    assert request.impact == 2
    assert not hasattr(request, "priority") or getattr(request, "priority", None) is None


def test_priority_solo_puede_ser_uno_de_los_cuatro_niveles() -> None:
    """Los valores de la matriz son siempre P1, P2, P3 o P4."""
    for urgency in (1, 2, 3):
        for impact in (1, 2, 3):
            assert calculate_priority(urgency, impact) in {
                Priority.P1,
                Priority.P2,
                Priority.P3,
                Priority.P4,
            }
