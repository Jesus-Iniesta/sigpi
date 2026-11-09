"""Pruebas de la emisión de avisos al cambiar el estatus (S4-07, HU-07.1).

- Iniciar la atención emite `request_status_changed`; resolver, `request_resolved`, y
  confirmar, `request_closed`, cada uno con un aviso por destinatario.
- El cuerpo trae folio, categoría, prioridad, técnico y fecha compromiso.
- Ningún evento avisa dos veces a la misma persona.
- `request_assigned` y `p1_unassigned` no tienen emisor hasta el Sprint 5: se prueban
  llamando al servicio directamente.
- El aviso se confirma junto con el cambio; si su escritura falla, el cambio no se guarda.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.core.permissions import RoleName
from app.db.base import Base
from app.domain.eventos import EventoAviso
from app.models.catalog import Categoria
from app.models.enums import (
    NotificationImportance,
    Priority,
    RequestChannel,
    RequestStatus,
    UserType,
)
from app.models.identity import Role, User, UserRole
from app.models.notification import Notification
from app.models.request import Request, RequestAssignment, RequestLog
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.repositories.notificacion_repository import NotificacionRepository
from app.services.notificacion_service import NotificacionService
from app.services.seguimiento_service import SeguimientoService

INICIO = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
FECHA_COMPROMISO = "01/10/2026 13:00 UTC"  # alta + 240 min de resolución


@pytest.fixture
def entorno():
    """SQLite con solicitante, técnico, dos jefes (uno inactivo), otra persona y una
    solicitud «Asignada» con SLA de 240 minutos."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {
        key: uuid.uuid4()
        for key in ("solicitante", "tecnico", "jefe", "jefe_inactivo", "otra", "solicitud")
    }
    nombres = {
        "solicitante": "Sara Solicitante",
        "tecnico": "Tomás Técnico",
        "jefe": "Julia Jefa",
        "jefe_inactivo": "Iván Inactivo",
        "otra": "Olga Otra",
    }

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            for key, nombre in nombres.items():
                session.add(
                    User(
                        id=ids[key],
                        institutional_id=f"u-{key}",
                        full_name=nombre,
                        email=f"{key}@example.test",
                        user_type=UserType.ACADEMIC,
                        is_active=key != "jefe_inactivo",
                    )
                )
            rol = Role(name=RoleName.SERVICE_MANAGER)
            session.add(rol)
            categoria = Categoria(area_id=uuid.uuid4(), name="Redes")
            session.add(categoria)
            acuerdo = ServiceLevelAgreement(name="Acuerdo general", is_default=True)
            session.add(acuerdo)
            await session.flush()
            for jefe in ("jefe", "jefe_inactivo"):
                session.add(UserRole(user_id=ids[jefe], role_id=rol.id))
            version = ServiceLevelVersion(
                agreement_id=acuerdo.id,
                version=1,
                priority=Priority.P2,
                first_response_minutes=30,
                resolution_minutes=240,
                valid_from=INICIO - timedelta(days=30),
            )
            session.add(version)
            await session.flush()
            session.add(
                Request(
                    id=ids["solicitud"],
                    requester_id=ids["solicitante"],
                    category_id=categoria.id,
                    service_level_version_id=version.id,
                    folio="SIG-0001",
                    title="Sin internet en el laboratorio",
                    description="No hay red.",
                    physical_location="Edificio B",
                    channel=RequestChannel.PORTAL,
                    status=RequestStatus.ASSIGNED,
                    priority=Priority.P2,
                    created_at=INICIO,
                )
            )
            await session.flush()
            session.add(
                RequestAssignment(
                    request_id=ids["solicitud"], technician_id=ids["tecnico"], assigned_at=INICIO
                )
            )
            await session.commit()

    asyncio.run(preparar())
    try:
        yield maker, ids
    finally:
        asyncio.run(engine.dispose())


def _correr(maker, escenario):
    async def correr():
        async with maker() as session:
            return await escenario(session)

    return asyncio.run(correr())


def _avisos(maker) -> list[Notification]:
    """Avisos confirmados, leídos en una sesión nueva (regla 7)."""

    async def leer(session):
        return list(await session.scalars(select(Notification).order_by(Notification.created_at)))

    return _correr(maker, leer)


def _por_destinatario(avisos: list[Notification]) -> dict[uuid.UUID, list[Notification]]:
    agrupados: dict[uuid.UUID, list[Notification]] = {}
    for aviso in avisos:
        agrupados.setdefault(aviso.recipient_id, []).append(aviso)
    return agrupados


def _assert_datos_de_la_historia(aviso: Notification, tecnico: str = "Tomás Técnico") -> None:
    for dato in ("SIG-0001", "Redes", "P2", tecnico, FECHA_COMPROMISO):
        assert dato in aviso.body, f"falta «{dato}» en el aviso: {aviso.body!r}"


def _iniciar(ids):
    async def escenario(session):
        return await SeguimientoService(session).iniciar_atencion(
            ids["solicitud"], ids["tecnico"], ahora=INICIO + timedelta(minutes=10)
        )

    return escenario


def _resolver(ids):
    async def escenario(session):
        return await SeguimientoService(session).resolver(
            ids["solicitud"],
            ids["tecnico"],
            "Se cambió el cable.",
            ahora=INICIO + timedelta(hours=1),
        )

    return escenario


def _confirmar(ids, autor: str = "solicitante"):
    async def escenario(session):
        return await SeguimientoService(session).confirmar(
            ids["solicitud"], ids[autor], ahora=INICIO + timedelta(hours=2)
        )

    return escenario


# ------------------------------------------------------- eventos con emisor


def test_iniciar_la_atencion_avisa_el_cambio_de_estatus_al_solicitante(entorno):
    maker, ids = entorno

    _correr(maker, _iniciar(ids))

    avisos = _avisos(maker)
    assert [a.recipient_id for a in avisos] == [ids["solicitante"]]
    aviso = avisos[0]
    assert aviso.subject == "Solicitud SIG-0001: En proceso"
    assert aviso.importance == NotificationImportance.NORMAL
    _assert_datos_de_la_historia(aviso)


def test_resolver_avisa_al_solicitante_con_request_resolved(entorno):
    maker, ids = entorno

    _correr(maker, _resolver(ids))

    avisos = _avisos(maker)
    assert [a.recipient_id for a in avisos] == [ids["solicitante"]]
    assert avisos[0].subject == "Solicitud SIG-0001 resuelta"
    assert "Confirma si la solución funcionó" in avisos[0].body
    _assert_datos_de_la_historia(avisos[0])


def test_confirmar_avisa_al_solicitante_y_al_tecnico_con_request_closed(entorno):
    maker, ids = entorno
    _correr(maker, _resolver(ids))

    _correr(maker, _confirmar(ids))

    cerrados = [a for a in _avisos(maker) if a.subject == "Solicitud SIG-0001 cerrada"]
    assert sorted(a.recipient_id for a in cerrados) == sorted([ids["solicitante"], ids["tecnico"]])
    for aviso in cerrados:
        _assert_datos_de_la_historia(aviso)


def test_el_ciclo_completo_no_avisa_dos_veces_a_nadie_por_evento(entorno):
    maker, ids = entorno

    for paso in (_iniciar(ids), _resolver(ids), _confirmar(ids)):
        _correr(maker, paso)

    por_persona = _por_destinatario(_avisos(maker))
    asuntos_solicitante = [a.subject for a in por_persona[ids["solicitante"]]]
    assert asuntos_solicitante == [
        "Solicitud SIG-0001: En proceso",
        "Solicitud SIG-0001 resuelta",
        "Solicitud SIG-0001 cerrada",
    ]
    assert [a.subject for a in por_persona[ids["tecnico"]]] == ["Solicitud SIG-0001 cerrada"]
    assert ids["otra"] not in por_persona
    assert ids["jefe"] not in por_persona


def test_si_el_solicitante_es_el_tecnico_recibe_un_solo_aviso_de_cierre(entorno):
    maker, ids = entorno

    async def tecnico_es_solicitante(session):
        request = await session.get(Request, ids["solicitud"])
        request.requester_id = ids["tecnico"]
        await session.commit()

    _correr(maker, tecnico_es_solicitante)
    _correr(maker, _resolver(ids))
    _correr(maker, _confirmar(ids, autor="tecnico"))

    cerrados = [a for a in _avisos(maker) if a.subject == "Solicitud SIG-0001 cerrada"]
    assert [a.recipient_id for a in cerrados] == [ids["tecnico"]]


def test_el_diagnostico_no_cambia_el_estatus_ni_avisa(entorno):
    maker, ids = entorno

    async def diagnosticar(session):
        return await SeguimientoService(session).registrar_diagnostico(
            ids["solicitud"], ids["tecnico"], "Cable dañado."
        )

    _correr(maker, diagnosticar)

    assert _avisos(maker) == []


# ---------------------------------------------- eventos sin emisor (Sprint 5)


def test_request_assigned_avisa_al_solicitante_y_al_tecnico(entorno):
    maker, ids = entorno

    async def escenario(session):
        avisos = await NotificacionService(session).emitir(
            EventoAviso.SOLICITUD_ASIGNADA, ids["solicitud"], ahora=INICIO
        )
        await session.commit()
        return avisos

    _correr(maker, escenario)

    avisos = _avisos(maker)
    assert sorted(a.recipient_id for a in avisos) == sorted([ids["solicitante"], ids["tecnico"]])
    for aviso in avisos:
        assert aviso.subject == "Solicitud SIG-0001 asignada"
        _assert_datos_de_la_historia(aviso)


def test_p1_unassigned_avisa_solo_a_los_jefes_activos_con_importancia_alta(entorno):
    maker, ids = entorno

    async def escenario(session):
        avisos = await NotificacionService(session).emitir(
            EventoAviso.P1_SIN_ASIGNAR, ids["solicitud"], ahora=INICIO
        )
        await session.commit()
        return avisos

    _correr(maker, escenario)

    avisos = _avisos(maker)
    assert [a.recipient_id for a in avisos] == [ids["jefe"]]
    assert avisos[0].importance == NotificationImportance.HIGH
    for dato in ("SIG-0001", "Redes", FECHA_COMPROMISO):
        assert dato in avisos[0].body


def test_emitir_no_confirma_la_transaccion(entorno):
    maker, ids = entorno

    async def escenario(session):
        await NotificacionService(session).emitir(EventoAviso.SOLICITUD_ASIGNADA, ids["solicitud"])
        await session.rollback()

    _correr(maker, escenario)

    assert _avisos(maker) == []


# ------------------------------------------------------------ transacción


def test_el_aviso_y_el_cambio_de_estatus_se_confirman_juntos(entorno):
    maker, ids = entorno

    _correr(maker, _resolver(ids))

    async def leer(session):
        return await session.get(Request, ids["solicitud"])

    assert _correr(maker, leer).status == RequestStatus.RESOLVED
    assert len(_avisos(maker)) == 1


@pytest.mark.parametrize("paso", [_iniciar, _resolver])
def test_si_falla_la_escritura_del_aviso_el_cambio_de_estatus_no_se_guarda(
    entorno, monkeypatch, paso
):
    maker, ids = entorno

    async def falla(self, avisos):
        raise RuntimeError("no se pudo escribir el aviso")

    monkeypatch.setattr(NotificacionRepository, "add_many", falla)

    with pytest.raises(RuntimeError, match="no se pudo escribir el aviso"):
        _correr(maker, paso(ids))

    async def leer(session):
        request = await session.get(Request, ids["solicitud"])
        logs = list(await session.scalars(select(RequestLog)))
        return request, logs

    request, logs = _correr(maker, leer)
    assert request.status == RequestStatus.ASSIGNED
    assert request.resolved_at is None
    assert request.first_response_at is None
    assert logs == []
    assert _avisos(maker) == []


def test_si_falla_el_aviso_de_cierre_la_solicitud_sigue_resuelta(entorno, monkeypatch):
    maker, ids = entorno
    _correr(maker, _resolver(ids))

    async def falla(self, avisos):
        raise RuntimeError("no se pudo escribir el aviso")

    monkeypatch.setattr(NotificacionRepository, "add_many", falla)

    with pytest.raises(RuntimeError):
        _correr(maker, _confirmar(ids))

    async def leer(session):
        return await session.get(Request, ids["solicitud"])

    request = _correr(maker, leer)
    assert request.status == RequestStatus.RESOLVED
    assert request.closed_at is None
