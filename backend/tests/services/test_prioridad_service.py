"""Pruebas del servicio de prioridad (S3-06, HU-02.3)."""

import pytest

from app.models.enums import Priority, RequestChannel
from app.models.request import Request
from app.services.prioridad_service import PrioridadInvalidaError, PrioridadService

MATRIZ = [
    (3, 1, Priority.P2),
    (3, 2, Priority.P1),
    (3, 3, Priority.P1),
    (2, 1, Priority.P3),
    (2, 2, Priority.P2),
    (2, 3, Priority.P1),
    (1, 1, Priority.P4),
    (1, 2, Priority.P3),
    (1, 3, Priority.P2),
]


def _solicitud(urgency: int | None, impact: int | None) -> Request:
    return Request(
        title="Prueba",
        description="Prueba",
        physical_location="Aula 1",
        channel=RequestChannel.PORTAL,
        urgency=urgency,
        impact=impact,
    )


@pytest.mark.parametrize(("urgency", "impact", "esperada"), MATRIZ)
def test_calcular_aplica_la_matriz(urgency: int, impact: int, esperada: Priority) -> None:
    assert PrioridadService().calcular(urgency, impact) is esperada


@pytest.mark.parametrize(("urgency", "impact"), [(None, 2), (2, None), (None, None)])
def test_calcular_sin_urgencia_o_impacto_devuelve_none(urgency, impact) -> None:
    assert PrioridadService().calcular(urgency, impact) is None


@pytest.mark.parametrize(("urgency", "impact"), [(0, 2), (2, 4), (True, 2), (2.0, 2), ("2", 2)])
def test_calcular_rechaza_valores_fuera_de_la_matriz(urgency, impact) -> None:
    with pytest.raises(PrioridadInvalidaError):
        PrioridadService().calcular(urgency, impact)


def test_aplicar_asigna_la_prioridad_a_la_solicitud() -> None:
    solicitud = _solicitud(3, 3)

    resultado = PrioridadService().aplicar(solicitud)

    assert resultado is Priority.P1
    assert solicitud.priority is Priority.P1


def test_aplicar_recalcula_cuando_cambian_urgencia_o_impacto() -> None:
    servicio = PrioridadService()
    solicitud = _solicitud(1, 1)
    servicio.aplicar(solicitud)
    assert solicitud.priority is Priority.P4

    solicitud.impact = 3
    servicio.aplicar(solicitud)

    assert solicitud.priority is Priority.P2


def test_aplicar_deja_la_prioridad_vacia_si_faltan_datos() -> None:
    solicitud = _solicitud(2, None)
    solicitud.priority = Priority.P1  # valor previo que no debe sobrevivir

    PrioridadService().aplicar(solicitud)

    assert solicitud.priority is None
