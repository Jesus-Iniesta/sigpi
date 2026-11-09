"""Pruebas del servicio y la API de avisos dentro de la aplicación (S4-05, HU-07.1).
- Un evento guarda un aviso por destinatario, con folio, categoría, prioridad, técnico y
  fecha compromiso.
- La plantilla de la base de datos manda sobre la de respaldo.
- Cada persona solo ve, cuenta y marca como leídos sus propios avisos.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.catalog import Categoria
from app.models.enums import (
    NotificationChannel,
    NotificationImportance,
    NotificationStatus,
    Priority,
    RequestChannel,
    RequestStatus,
    UserType,
    WaitReason,
)
from app.models.identity import User
from app.models.notification import NotificationTemplate
from app.models.request import Request, RequestAssignment, RequestSlaPause
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.services.notificacion_service import (
    EVENTO_SOLICITUD_CERRADA,
    EVENTO_SOLICITUD_REGISTRADA,
    NotificacionService,
)

INICIO = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


@pytest.fixture
def entorno():
    """Base SQLite con tres personas y una solicitud asignada con SLA de 240 minutos."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {
        key: uuid.uuid4() for key in ("solicitante", "tecnico", "otra", "categoria", "solicitud")
    }

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            for key, nombre in (
                ("solicitante", "Sara Solicitante"),
                ("tecnico", "Tomás Técnico"),
                ("otra", "Olga Otra"),
            ):
                session.add(
                    User(
                        id=ids[key],
                        institutional_id=f"u-{ids[key].hex[:8]}",
                        full_name=nombre,
                        email=f"{key}@example.test",
                        user_type=UserType.ACADEMIC,
                    )
                )
            session.add(Categoria(id=ids["categoria"], area_id=uuid.uuid4(), name="Redes"))
            acuerdo = ServiceLevelAgreement(name="Acuerdo general", is_default=True)
            session.add(acuerdo)
            await session.flush()
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
                    category_id=ids["categoria"],
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


def _ejecutar(maker, escenario):
    """Corre `escenario(servicio)` con una sesión nueva y devuelve su resultado."""

    async def correr():
        async with maker() as session:
            return await escenario(NotificacionService(session))

    return asyncio.run(correr())


def _sembrar(maker, coro_fn) -> None:
    async def correr():
        async with maker() as session:
            await coro_fn(session)
            await session.commit()

    asyncio.run(correr())


def _utc(texto: str) -> datetime:
    """Lee una fecha ISO de la API; SQLite la devuelve sin zona, así que se asume UTC."""
    valor = datetime.fromisoformat(texto)
    return valor if valor.tzinfo else valor.replace(tzinfo=UTC)


def _como(user_id: uuid.UUID) -> SimpleNamespace:
    """Usuario autenticado: `/notificaciones` solo usa su `id`."""
    return SimpleNamespace(id=user_id, is_active=True, roles=[])


# ---------------------------------------------------------------- servicio


def test_un_evento_guarda_un_aviso_por_destinatario_con_los_datos_de_la_historia(entorno):
    maker, ids = entorno

    async def escenario(servicio):
        # El solicitante aparece dos veces: debe recibir un solo aviso.
        return await servicio.notificar_evento(
            EVENTO_SOLICITUD_REGISTRADA,
            ids["solicitud"],
            [ids["solicitante"], ids["tecnico"], ids["solicitante"]],
            ahora=INICIO,
        )

    avisos = _ejecutar(maker, escenario)

    assert {a.recipient_id for a in avisos} == {ids["solicitante"], ids["tecnico"]}
    assert len(avisos) == 2
    aviso = avisos[0]
    assert aviso.channel == NotificationChannel.IN_APP
    assert aviso.status == NotificationStatus.SENT
    assert aviso.importance == NotificationImportance.NORMAL
    assert aviso.read_at is None
    assert aviso.sent_at == INICIO
    assert aviso.subject == "Solicitud SIG-0001 registrada"
    for dato in ("SIG-0001", "Redes", "P2", "Tomás Técnico", "01/10/2026 13:00 UTC"):
        assert dato in aviso.body


def test_la_fecha_compromiso_suma_el_tiempo_en_espera(entorno):
    maker, ids = entorno

    async def pausa(session):
        session.add(
            RequestSlaPause(
                request_id=ids["solicitud"],
                reason=WaitReason.EXTERNAL_INPUT,
                started_by_id=ids["tecnico"],
                started_at=INICIO + timedelta(minutes=30),
                ended_at=INICIO + timedelta(minutes=90),
            )
        )

    _sembrar(maker, pausa)

    async def escenario(servicio):
        return await servicio.notificar_evento(
            EVENTO_SOLICITUD_REGISTRADA, ids["solicitud"], [ids["solicitante"]], ahora=INICIO
        )

    (aviso,) = _ejecutar(maker, escenario)

    # 09:00 + 240 min de SLA + 60 min en espera = 14:00.
    assert "01/10/2026 14:00 UTC" in aviso.body


def test_sin_tecnico_ni_sla_ni_categoria_el_aviso_usa_valores_por_defecto(entorno):
    maker, ids = entorno
    solicitud_id = uuid.uuid4()

    async def sin_datos(session):
        session.add(
            Request(
                id=solicitud_id,
                requester_id=ids["solicitante"],
                folio="SIG-0002",
                title="Pantalla rota",
                description="Se rompió.",
                physical_location="Edificio A",
                channel=RequestChannel.PORTAL,
                status=RequestStatus.REGISTERED,
                created_at=INICIO,
            )
        )

    _sembrar(maker, sin_datos)

    async def escenario(servicio):
        return await servicio.notificar_evento(
            EVENTO_SOLICITUD_REGISTRADA, solicitud_id, [ids["solicitante"]], ahora=INICIO
        )

    (aviso,) = _ejecutar(maker, escenario)

    assert "Sin asignar" in aviso.body
    assert "Sin clasificar" in aviso.body
    assert "Fecha compromiso: —" in aviso.body


def test_un_aviso_de_alta_importancia_se_guarda_como_tal(entorno):
    maker, ids = entorno

    async def escenario(servicio):
        return await servicio.notificar_evento(
            EVENTO_SOLICITUD_CERRADA,
            ids["solicitud"],
            [ids["tecnico"]],
            importance=NotificationImportance.HIGH,
        )

    (aviso,) = _ejecutar(maker, escenario)

    assert aviso.importance == NotificationImportance.HIGH


def test_la_plantilla_de_la_base_tiene_prioridad_y_un_campo_faltante_no_falla(entorno):
    maker, ids = entorno
    plantilla_id = uuid.uuid4()

    async def plantilla(session):
        session.add(
            NotificationTemplate(
                id=plantilla_id,
                event_code=EVENTO_SOLICITUD_CERRADA,
                subject_template="Cerrada {folio}",
                body_template="Hola {folio} {campo_inexistente}",
            )
        )

    _sembrar(maker, plantilla)

    async def escenario(servicio):
        return await servicio.notificar_evento(
            EVENTO_SOLICITUD_CERRADA, ids["solicitud"], [ids["solicitante"]]
        )

    (aviso,) = _ejecutar(maker, escenario)

    assert aviso.template_id == plantilla_id
    assert aviso.subject == "Cerrada SIG-0001"
    assert aviso.body == "Hola SIG-0001 —"


def test_un_evento_sin_plantilla_se_rechaza(entorno):
    maker, ids = entorno

    async def escenario(servicio):
        return await servicio.notificar_evento(
            "evento_inventado", ids["solicitud"], [ids["solicitante"]]
        )

    with pytest.raises(BusinessRuleError):
        _ejecutar(maker, escenario)


def test_una_solicitud_inexistente_se_rechaza(entorno):
    maker, ids = entorno

    async def escenario(servicio):
        return await servicio.notificar_evento(
            EVENTO_SOLICITUD_REGISTRADA, uuid.uuid4(), [ids["solicitante"]]
        )

    with pytest.raises(NotFoundError):
        _ejecutar(maker, escenario)


def test_sin_destinatarios_no_se_guarda_nada(entorno):
    maker, ids = entorno

    async def escenario(servicio):
        avisos = await servicio.notificar_evento(EVENTO_SOLICITUD_REGISTRADA, ids["solicitud"], [])
        return avisos, await servicio.listar(ids["solicitante"])

    avisos, guardados = _ejecutar(maker, escenario)

    assert avisos == []
    assert guardados == []


# --------------------------------------------------------------------- API


@pytest.fixture
def cliente(entorno):
    """Cliente HTTP autenticado como la persona solicitante, con avisos propios y ajenos."""
    maker, ids = entorno

    async def sembrar_avisos(servicio):
        # Dos avisos para la solicitante (el segundo más reciente) y uno para la técnica.
        await servicio.notificar_evento(
            EVENTO_SOLICITUD_REGISTRADA, ids["solicitud"], [ids["solicitante"]], ahora=INICIO
        )
        await servicio.notificar_evento(
            EVENTO_SOLICITUD_CERRADA,
            ids["solicitud"],
            [ids["solicitante"], ids["otra"]],
            ahora=INICIO + timedelta(minutes=5),
        )

    _ejecutar(maker, sembrar_avisos)

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como(ids["solicitante"])
    try:
        yield TestClient(fastapi_app), ids, maker
    finally:
        fastapi_app.dependency_overrides.clear()


def test_lista_solo_los_avisos_propios_del_mas_reciente_al_mas_antiguo(cliente):
    http, _ids, _maker = cliente

    respuesta = http.get("/notificaciones")

    assert respuesta.status_code == 200
    asuntos = [aviso["subject"] for aviso in respuesta.json()]
    assert asuntos == ["Solicitud SIG-0001 cerrada", "Solicitud SIG-0001 registrada"]
    primero = respuesta.json()[0]
    assert primero["request_folio"] == "SIG-0001"
    assert primero["is_read"] is False
    assert primero["importance"] == "normal"


def test_el_contador_cuenta_solo_los_no_leidos_propios(cliente):
    http, _ids, _maker = cliente

    assert http.get("/notificaciones/contador").json() == {"unread": 2}


def test_marcar_leido_baja_el_contador_y_se_puede_filtrar_por_no_leidos(cliente):
    http, _ids, _maker = cliente
    aviso_id = http.get("/notificaciones").json()[0]["id"]

    marcado = http.post(f"/notificaciones/{aviso_id}/leer")

    assert marcado.status_code == 200
    assert marcado.json()["is_read"] is True
    assert marcado.json()["read_at"] is not None
    assert http.get("/notificaciones/contador").json() == {"unread": 1}
    pendientes = http.get("/notificaciones", params={"only_unread": True}).json()
    assert [aviso["subject"] for aviso in pendientes] == ["Solicitud SIG-0001 registrada"]


def test_marcar_leido_dos_veces_conserva_la_primera_fecha(cliente):
    http, _ids, _maker = cliente
    aviso_id = http.get("/notificaciones").json()[0]["id"]

    primera = http.post(f"/notificaciones/{aviso_id}/leer").json()["read_at"]
    segunda = http.post(f"/notificaciones/{aviso_id}/leer").json()["read_at"]

    assert _utc(primera) == _utc(segunda)


def test_no_se_puede_marcar_el_aviso_de_otra_persona(cliente):
    http, ids, maker = cliente

    async def de_otra(servicio):
        return await servicio.listar(ids["otra"])

    (aviso_ajeno,) = _ejecutar(maker, de_otra)

    respuesta = http.post(f"/notificaciones/{aviso_ajeno.id}/leer")

    assert respuesta.status_code == 404
    assert respuesta.json()["code"] == "not_found"
    assert _ejecutar(maker, lambda s: s.contar_no_leidos(ids["otra"])) == 1


def test_marcar_todas_como_leidas_no_toca_los_avisos_ajenos(cliente):
    http, ids, maker = cliente

    respuesta = http.post("/notificaciones/leer-todas")

    assert respuesta.json() == {"updated": 2}
    assert http.get("/notificaciones/contador").json() == {"unread": 0}
    assert _ejecutar(maker, lambda s: s.contar_no_leidos(ids["otra"])) == 1


def test_la_paginacion_respeta_limit_y_offset(cliente):
    http, _ids, _maker = cliente

    segunda_pagina = http.get("/notificaciones", params={"limit": 1, "offset": 1}).json()

    assert [aviso["subject"] for aviso in segunda_pagina] == ["Solicitud SIG-0001 registrada"]


def test_sin_sesion_la_api_responde_401(entorno):
    maker, _ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    try:
        respuesta = TestClient(fastapi_app).get("/notificaciones")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert respuesta.status_code == 401
