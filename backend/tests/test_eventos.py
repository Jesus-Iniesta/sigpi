"""Catálogo de eventos, plantillas y semilla de avisos (S4-04, HU-07.1)."""

import uuid

import pytest

from app.domain.eventos import (
    CATALOGO_EVENTOS,
    ROL_JEFES,
    Destinatario,
    EventoAviso,
    destinatarios,
    importancia,
)
from app.models.enums import NotificationImportance
from app.models.notification import NotificationTemplate
from app.seeds import service
from app.services import notificacion_service
from app.templates.avisos import PLANTILLAS_AVISO

SOLICITANTE = uuid.uuid4()
TECNICO = uuid.uuid4()
JEFE_A = uuid.uuid4()
JEFE_B = uuid.uuid4()


# ------------------------------------------------------------------ catálogo


@pytest.mark.parametrize("evento", list(EventoAviso))
def test_cada_evento_tiene_plantilla_importancia_y_destinatarios(evento):
    asunto, cuerpo = PLANTILLAS_AVISO[evento]
    assert asunto.strip() and cuerpo.strip()
    regla = CATALOGO_EVENTOS[evento]
    assert isinstance(regla.importancia, NotificationImportance)
    assert regla.destinatarios


def test_catalogo_y_plantillas_cubren_exactamente_los_eventos():
    assert set(CATALOGO_EVENTOS) == set(EventoAviso)
    assert set(PLANTILLAS_AVISO) == set(EventoAviso)


def test_codigos_de_evento_conservan_su_valor():
    assert {e.value for e in EventoAviso} == {
        "request_registered",
        "request_assigned",
        "request_status_changed",
        "request_resolved",
        "request_closed",
        "sla_risk",
        "p1_unassigned",
    }


def test_solo_riesgo_sla_y_p1_sin_asignar_son_de_alta_importancia():
    altas = {e for e in EventoAviso if importancia(e) == NotificationImportance.HIGH}
    assert altas == {EventoAviso.RIESGO_SLA, EventoAviso.P1_SIN_ASIGNAR}


def test_los_jefes_son_el_rol_service_manager():
    assert ROL_JEFES == "service_manager"


def test_el_servicio_usa_los_codigos_y_plantillas_del_catalogo():
    assert notificacion_service._PLANTILLAS_RESPALDO is PLANTILLAS_AVISO
    assert notificacion_service.EVENTOS_CONOCIDOS == frozenset(EventoAviso)
    assert notificacion_service.EVENTO_RIESGO_SLA == "sla_risk"


# ------------------------------------------------------------- destinatarios


@pytest.mark.parametrize(
    ("evento", "esperados"),
    [
        (EventoAviso.SOLICITUD_REGISTRADA, [SOLICITANTE]),
        (EventoAviso.SOLICITUD_ASIGNADA, [SOLICITANTE, TECNICO]),
        (EventoAviso.ESTATUS_CAMBIADO, [SOLICITANTE]),
        (EventoAviso.SOLICITUD_RESUELTA, [SOLICITANTE]),
        (EventoAviso.SOLICITUD_CERRADA, [SOLICITANTE, TECNICO]),
        (EventoAviso.RIESGO_SLA, [TECNICO, JEFE_A, JEFE_B]),
        (EventoAviso.P1_SIN_ASIGNAR, [JEFE_A, JEFE_B]),
    ],
)
def test_destinatarios_por_evento(evento, esperados):
    assert destinatarios(evento, SOLICITANTE, TECNICO, [JEFE_A, JEFE_B]) == esperados


def test_destinatarios_acepta_el_codigo_como_texto():
    assert destinatarios("request_assigned", SOLICITANTE, TECNICO, []) == [SOLICITANTE, TECNICO]


@pytest.mark.parametrize("evento", list(EventoAviso))
def test_destinatarios_ignora_none(evento):
    resultado = destinatarios(evento, None, None, [None, JEFE_A])  # type: ignore[list-item]
    assert None not in resultado


def test_destinatarios_sin_tecnico_ni_jefes():
    assert destinatarios(EventoAviso.RIESGO_SLA, SOLICITANTE, None, None) == []
    assert destinatarios(EventoAviso.SOLICITUD_CERRADA, SOLICITANTE, None) == [SOLICITANTE]


@pytest.mark.parametrize("evento", list(EventoAviso))
def test_destinatarios_nunca_repite(evento):
    # El técnico también es jefe y el solicitante es su propio técnico.
    resultado = destinatarios(evento, SOLICITANTE, SOLICITANTE, [SOLICITANTE, JEFE_A, JEFE_A])
    assert len(resultado) == len(set(resultado))


def test_regla_de_destinatarios_usa_los_papeles_del_issue():
    assert CATALOGO_EVENTOS[EventoAviso.P1_SIN_ASIGNAR].destinatarios == (Destinatario.JEFES,)


def test_evento_desconocido_es_error_de_programacion():
    with pytest.raises(ValueError):
        destinatarios("no_existe", SOLICITANTE, TECNICO, [])


# -------------------------------------------------------------------- semilla


class _SesionFalsa:
    def __init__(self):
        self.plantillas: dict[str, NotificationTemplate] = {}
        self.commits = 0

    async def scalar(self, query):
        return self.plantillas.get(query.whereclause.right.value)

    def add(self, entidad):
        self.plantillas[entidad.event_code] = entidad

    async def commit(self):
        self.commits += 1


class _Contexto:
    def __init__(self, sesion):
        self.sesion = sesion

    async def __aenter__(self):
        return self.sesion

    async def __aexit__(self, *_):
        return False


@pytest.mark.asyncio
async def test_semilla_de_plantillas_es_idempotente(monkeypatch):
    sesion = _SesionFalsa()
    monkeypatch.setattr(service, "_session_factory", lambda: lambda: _Contexto(sesion))

    assert await service.run_seed_notification_templates() == len(EventoAviso)
    assert await service.run_seed_notification_templates() == 0

    assert set(sesion.plantillas) == {e.value for e in EventoAviso}
    assert sesion.commits == 2
    registrada = sesion.plantillas["request_registered"]
    assert type(registrada.event_code) is str
    assert (registrada.subject_template, registrada.body_template) == PLANTILLAS_AVISO[
        EventoAviso.SOLICITUD_REGISTRADA
    ]


@pytest.mark.asyncio
async def test_semilla_no_sobrescribe_plantillas_existentes(monkeypatch):
    sesion = _SesionFalsa()
    editada = NotificationTemplate(
        event_code="sla_risk", subject_template="Editado", body_template="Editado"
    )
    sesion.plantillas["sla_risk"] = editada
    monkeypatch.setattr(service, "_session_factory", lambda: lambda: _Contexto(sesion))

    assert await service.run_seed_notification_templates() == len(EventoAviso) - 1
    assert sesion.plantillas["sla_risk"] is editada
    assert editada.subject_template == "Editado"


@pytest.mark.asyncio
async def test_run_all_incluye_las_plantillas(monkeypatch):
    async def cero(*_args, **_kwargs):
        return 0

    async def prioridades():
        return ()

    for nombre in (
        "run_seed_organizational_units",
        "run_seed_area",
        "run_seed_categories",
        "run_seed_service_areas",
        "run_seed_specialties",
        "run_seed_shifts",
        "run_seed_users",
    ):
        monkeypatch.setattr(service, nombre, cero)
    monkeypatch.setattr(service, "run_seed_priorities", prioridades)

    async def plantillas():
        return 7

    monkeypatch.setattr(service, "run_seed_notification_templates", plantillas)

    conteos = await service.run_all()
    assert conteos["notification_templates"] == 7


def test_comando_notifications_existe():
    from typer.testing import CliRunner

    from app.seeds.__main__ import app

    resultado = CliRunner().invoke(app, ["--help"])
    assert "notifications" in resultado.output
