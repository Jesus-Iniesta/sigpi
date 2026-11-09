"""Pruebas de la alerta de riesgo del SLA al técnico y al Jefe (S4-09, HU-07.2).

- Al cruzar el 80 % se crean avisos de alta importancia para el técnico y cada jefe,
  una sola vez.
- Si la escritura del aviso falla, `sla_risk_alerted_at` sigue vacío.
- Una solicitud sin técnico avisa solo a los jefes.
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
from app.models.enums import (
    NotificationImportance,
    Priority,
    RequestChannel,
    RequestStatus,
    UserType,
)
from app.models.identity import Role, User, UserRole
from app.models.notification import Notification
from app.models.request import Request, RequestAssignment
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.repositories.notificacion_repository import NotificacionRepository
from app.services.notificacion_service import SIN_TECNICO_ASIGNADO, NotificacionService
from app.services.sla_monitor_service import SlaMonitorService, emitir_alertas_riesgo

INICIO = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
RESOLUCION = 100  # con 100 minutos comprometidos, cada minuto equivale a un 1 %


def _min(n: float) -> datetime:
    return INICIO + timedelta(minutes=n)


@pytest.fixture
def entorno():
    """Solicitante, técnico, dos jefes activos, un jefe inactivo y un administrador."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    claves = ("solicitante", "tecnico", "jefe_a", "jefe_b", "jefe_inactivo", "admin", "version")
    ids = {clave: uuid.uuid4() for clave in claves}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            for clave in ("solicitante", "tecnico", "jefe_a", "jefe_b", "jefe_inactivo", "admin"):
                session.add(
                    User(
                        id=ids[clave],
                        institutional_id=f"u-{ids[clave].hex[:8]}",
                        full_name=clave.replace("_", " ").title(),
                        email=f"{clave}@example.test",
                        user_type=UserType.ADMINISTRATIVE,
                        is_active=clave != "jefe_inactivo",
                    )
                )
            jefe = Role(name=RoleName.SERVICE_MANAGER)
            admin = Role(name=RoleName.ADMINISTRATOR)
            session.add_all([jefe, admin])
            await session.flush()
            for clave in ("jefe_a", "jefe_b", "jefe_inactivo"):
                session.add(UserRole(user_id=ids[clave], role_id=jefe.id))
            session.add(UserRole(user_id=ids["admin"], role_id=admin.id))
            acuerdo = ServiceLevelAgreement(name="Acuerdo general", is_default=True)
            session.add(acuerdo)
            await session.flush()
            session.add(
                ServiceLevelVersion(
                    id=ids["version"],
                    agreement_id=acuerdo.id,
                    version=1,
                    priority=Priority.P2,
                    first_response_minutes=30,
                    resolution_minutes=RESOLUCION,
                    valid_from=INICIO - timedelta(days=30),
                )
            )
            await session.commit()

    asyncio.run(preparar())
    try:
        yield maker, ids
    finally:
        asyncio.run(engine.dispose())


def _crear(maker, ids, *, con_tecnico: bool = True) -> uuid.UUID:
    async def crear() -> uuid.UUID:
        async with maker() as session:
            request = Request(
                requester_id=ids["solicitante"],
                folio=f"SIG-{uuid.uuid4().hex[:6]}",
                title="Sin red en el laboratorio",
                description="Sin red",
                physical_location="Edificio B",
                channel=RequestChannel.PORTAL,
                status=RequestStatus.IN_PROGRESS if con_tecnico else RequestStatus.CLASSIFIED,
                priority=Priority.P2,
                service_level_version_id=ids["version"],
                created_at=INICIO,
            )
            session.add(request)
            await session.flush()
            if con_tecnico:
                session.add(
                    RequestAssignment(
                        request_id=request.id, technician_id=ids["tecnico"], assigned_at=INICIO
                    )
                )
            await session.commit()
            return request.id

    return asyncio.run(crear())


def _vuelta(maker, ahora: datetime, al_detectar=emitir_alertas_riesgo) -> list[uuid.UUID]:
    async def correr() -> list[uuid.UUID]:
        async with maker() as session:
            detectadas = await SlaMonitorService(session).ejecutar_vuelta(
                ahora, al_detectar=al_detectar
            )
            return [r.id for r in detectadas]

    return asyncio.run(correr())


def _avisos(maker, request_id: uuid.UUID) -> list[Notification]:
    async def leer() -> list[Notification]:
        async with maker() as session:
            result = await session.scalars(
                select(Notification).where(Notification.request_id == request_id)
            )
            return list(result)

    return asyncio.run(leer())


def _alertada_en(maker, request_id: uuid.UUID) -> datetime | None:
    async def leer() -> datetime | None:
        async with maker() as session:
            request = await session.get(Request, request_id)
            return request.sla_risk_alerted_at

    return asyncio.run(leer())


# --- criterio 1: técnico y cada jefe, alta importancia, una sola vez -------------


def test_al_cruzar_el_80_avisa_al_tecnico_y_a_cada_jefe_activo(entorno) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids)

    assert _vuelta(maker, _min(80)) == [request_id]

    avisos = _avisos(maker, request_id)
    assert {a.recipient_id for a in avisos} == {ids["tecnico"], ids["jefe_a"], ids["jefe_b"]}
    assert all(a.importance == NotificationImportance.HIGH for a in avisos)
    assert all("Tiempo consumido: 80 %" in a.body for a in avisos)
    assert all("Tiempo restante: 20 min" in a.body for a in avisos)
    assert all(SIN_TECNICO_ASIGNADO not in a.body for a in avisos)
    assert _alertada_en(maker, request_id) is not None


def test_la_alerta_se_emite_una_sola_vez(entorno) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids)

    _vuelta(maker, _min(80))
    assert _vuelta(maker, _min(90)) == []
    assert _vuelta(maker, _min(120)) == []

    assert len(_avisos(maker, request_id)) == 3


def test_antes_del_80_no_hay_aviso(entorno) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids)

    assert _vuelta(maker, _min(79)) == []
    assert _avisos(maker, request_id) == []


# --- criterio 2: si el aviso falla no se marca --------------------------------------


def test_si_falla_la_escritura_del_aviso_no_se_marca_y_se_reintenta(entorno, monkeypatch) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids)
    original = NotificacionRepository.add_many

    async def falla(_self, _avisos) -> None:
        raise RuntimeError("no se pudo guardar el aviso")

    monkeypatch.setattr(NotificacionRepository, "add_many", falla)
    with pytest.raises(RuntimeError):
        _vuelta(maker, _min(85))

    assert _alertada_en(maker, request_id) is None
    assert _avisos(maker, request_id) == []

    # En la siguiente vuelta, ya sin falla, se avisa y se marca.
    monkeypatch.setattr(NotificacionRepository, "add_many", original)
    assert _vuelta(maker, _min(86)) == [request_id]
    assert len(_avisos(maker, request_id)) == 3
    assert _alertada_en(maker, request_id) is not None


def test_si_falla_el_aviso_de_una_segunda_solicitud_no_queda_nada_a_medias(
    entorno, monkeypatch
) -> None:
    maker, ids = entorno
    primera = _crear(maker, ids)
    segunda = _crear(maker, ids)
    original = NotificacionRepository.add_many
    llamadas = 0

    async def falla_la_segunda(self, avisos):
        nonlocal llamadas
        llamadas += 1
        if llamadas == 2:
            raise RuntimeError("no se pudo guardar el aviso")
        return await original(self, avisos)

    monkeypatch.setattr(NotificacionRepository, "add_many", falla_la_segunda)
    with pytest.raises(RuntimeError):
        _vuelta(maker, _min(85))

    for request_id in (primera, segunda):
        assert _alertada_en(maker, request_id) is None
        assert _avisos(maker, request_id) == []


def test_alerta_riesgo_no_confirma_la_transaccion(entorno) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids)

    async def avisar() -> int:
        async with maker() as session:
            request = await session.get(Request, request_id)
            avisos = await NotificacionService(session).alerta_riesgo(request, _min(85))
            return len(avisos)

    assert asyncio.run(avisar()) == 3
    # La sesión se cerró sin commit: nada quedó guardado.
    assert _avisos(maker, request_id) == []


def test_la_vuelta_confirma_aviso_y_marca_juntos(entorno) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids)

    _vuelta(maker, _min(85))

    avisos = _avisos(maker, request_id)
    assert len(avisos) == 3
    alertada = _alertada_en(maker, request_id)
    assert alertada is not None
    assert alertada.replace(tzinfo=UTC) == _min(85)


# --- criterio 3: sin técnico, solo jefes ---------------------------------------------


def test_sin_tecnico_avisa_solo_a_los_jefes_y_lo_anota(entorno) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids, con_tecnico=False)

    assert _vuelta(maker, _min(95)) == [request_id]

    avisos = _avisos(maker, request_id)
    assert {a.recipient_id for a in avisos} == {ids["jefe_a"], ids["jefe_b"]}
    assert all(SIN_TECNICO_ASIGNADO in a.body for a in avisos)
    assert all("Tiempo restante: 5 min" in a.body for a in avisos)


def test_el_tiempo_restante_no_es_negativo_si_ya_vencio(entorno) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids)

    _vuelta(maker, _min(250))

    avisos = _avisos(maker, request_id)
    assert all("Tiempo consumido: 250 %" in a.body for a in avisos)
    assert all("Tiempo restante: 0 min" in a.body for a in avisos)


def test_la_consulta_de_jefes_excluye_inactivos_y_otros_roles(entorno) -> None:
    maker, ids = entorno

    async def jefes() -> list[uuid.UUID]:
        async with maker() as session:
            repo = NotificacionRepository(session)
            return await repo.list_active_user_ids_with_role(RoleName.SERVICE_MANAGER)

    assert set(asyncio.run(jefes())) == {ids["jefe_a"], ids["jefe_b"]}
