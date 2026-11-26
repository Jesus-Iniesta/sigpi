"""Reglas puras del puntaje de asignación de técnicos (S5-03, HU-03.1)."""

import uuid

from app.domain.asignacion import (
    PUNTOS_CARGA_MAX,
    PUNTOS_ESPECIALIDAD,
    PUNTOS_TURNO,
    TecnicoCandidato,
    estado_al_asignar,
    proponer,
    puede_asignarse,
    turno_vigente,
)
from app.models.enums import RequestStatus

REDES = uuid.uuid4()
OTRA = uuid.uuid4()
MEDIODIA = 12 * 60


def _tecnico(nombre: str, **datos) -> TecnicoCandidato:
    return TecnicoCandidato(
        id=uuid.uuid4(), nombre=nombre, activo=datos.pop("activo", True), **datos
    )


def test_especialidad_y_menor_carga_quedan_primero_con_desglose():
    experto_libre = _tecnico("Ana", categorias=frozenset({REDES}), carga=0)
    experto_cargado = _tecnico("Beto", categorias=frozenset({REDES}), carga=4)
    sin_especialidad = _tecnico(
        "Ciro",
        categorias=frozenset({OTRA}),
        carga=0,
        turno="Matutino",
        turno_inicio=7 * 60,
        turno_fin=15 * 60,
    )

    propuesta = proponer([sin_especialidad, experto_cargado, experto_libre], REDES, MEDIODIA)

    assert [p.nombre for p in propuesta] == ["Ana", "Beto", "Ciro"]
    assert propuesta[0].score == PUNTOS_ESPECIALIDAD + PUNTOS_CARGA_MAX
    assert propuesta[1].score == PUNTOS_ESPECIALIDAD + PUNTOS_CARGA_MAX - 4
    assert propuesta[2].score == PUNTOS_TURNO + PUNTOS_CARGA_MAX
    conceptos = [c.concepto for c in propuesta[0].desglose]
    assert conceptos == ["Especialidad", "Turno", "Carga"]
    assert "Especialidad +100" in propuesta[0].score_breakdown
    assert "Turno +20 (Matutino: en turno)" in propuesta[2].score_breakdown


def test_excluye_inactivos():
    activo = _tecnico("Ana")
    inactivo = _tecnico("Beto", activo=False)

    assert [p.technician_id for p in proponer([inactivo, activo], None, MEDIODIA)] == [activo.id]


def test_turno_vigente_incluye_turnos_que_cruzan_la_medianoche():
    assert turno_vigente(7 * 60, 15 * 60, MEDIODIA)
    assert not turno_vigente(7 * 60, 15 * 60, 15 * 60)
    assert turno_vigente(22 * 60, 6 * 60, 23 * 60)
    assert turno_vigente(22 * 60, 6 * 60, 60)
    assert not turno_vigente(22 * 60, 6 * 60, MEDIODIA)
    assert not turno_vigente(None, None, MEDIODIA)


def test_carga_nunca_resta_puntos():
    saturado = _tecnico("Ana", carga=50)

    assert proponer([saturado], None, MEDIODIA)[0].score == 0


def test_estados_asignables():
    assert estado_al_asignar(RequestStatus.REGISTERED) == RequestStatus.ASSIGNED
    assert estado_al_asignar(RequestStatus.CLASSIFIED) == RequestStatus.ASSIGNED
    assert estado_al_asignar(RequestStatus.IN_PROGRESS) == RequestStatus.IN_PROGRESS
    assert not puede_asignarse(RequestStatus.CLOSED)
    assert not puede_asignarse(RequestStatus.RESOLVED)
    assert puede_asignarse(RequestStatus.PENDING_REVIEW)
