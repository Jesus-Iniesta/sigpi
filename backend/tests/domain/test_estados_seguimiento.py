"""Reglas de estados del seguimiento y la resolución (S3-12, HU-04.1)."""

import pytest

from app.domain.estados import puede_diagnosticar, puede_iniciar, puede_resolver
from app.models.enums import RequestStatus

OTROS = [
    RequestStatus.REGISTERED,
    RequestStatus.PENDING_VERIFICATION,
    RequestStatus.WAITING,
    RequestStatus.RESOLVED,
    RequestStatus.CLOSED,
]


def test_solo_una_solicitud_asignada_puede_iniciarse() -> None:
    assert puede_iniciar(RequestStatus.ASSIGNED)
    assert not puede_iniciar(RequestStatus.IN_PROGRESS)
    for status in OTROS:
        assert not puede_iniciar(status)


@pytest.mark.parametrize("status", [RequestStatus.ASSIGNED, RequestStatus.IN_PROGRESS])
def test_se_puede_resolver_desde_asignada_o_en_proceso(status: RequestStatus) -> None:
    assert puede_resolver(status)


@pytest.mark.parametrize("status", OTROS)
def test_no_se_puede_resolver_desde_otros_estados(status: RequestStatus) -> None:
    assert not puede_resolver(status)


def test_el_diagnostico_se_registra_durante_la_atencion() -> None:
    assert puede_diagnosticar(RequestStatus.ASSIGNED)
    assert puede_diagnosticar(RequestStatus.IN_PROGRESS)
    assert puede_diagnosticar(RequestStatus.WAITING)
    assert not puede_diagnosticar(RequestStatus.PENDING_VERIFICATION)
    assert not puede_diagnosticar(RequestStatus.RESOLVED)
