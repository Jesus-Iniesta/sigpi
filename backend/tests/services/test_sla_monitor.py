"""Pruebas del monitor del umbral de riesgo del SLA (S4-08, HU-07.2)."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.main as main_module
import app.models  # noqa: F401
from app.core.config import Settings, settings
from app.db.base import Base
from app.models.enums import Priority, RequestChannel, RequestStatus, UserType
from app.models.identity import User
from app.models.request import Request, RequestSlaPause
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.services.sla_monitor_service import (
    SlaMonitorService,
    SolicitudNoEncontradaError,
    ejecutar_monitor,
)

INICIO = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
# Con 100 minutos comprometidos, cada minuto efectivo equivale a un 1 %.
RESOLUCION = 100


def _min(n: float) -> datetime:
    return INICIO + timedelta(minutes=n)


@pytest.fixture
def entorno():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"requester": uuid.uuid4(), "version": uuid.uuid4()}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            uid = ids["requester"]
            session.add(
                User(
                    id=uid,
                    institutional_id=f"u-{uid.hex[:8]}",
                    full_name="Solicitante",
                    email=f"{uid.hex[:8]}@example.test",
                    user_type=UserType.ACADEMIC,
                    is_active=True,
                )
            )
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


def _crear(
    maker,
    ids,
    *,
    status: RequestStatus = RequestStatus.IN_PROGRESS,
    con_acuerdo: bool = True,
    pausas: tuple[tuple[float, float | None], ...] = (),
) -> uuid.UUID:
    async def crear() -> uuid.UUID:
        async with maker() as session:
            request = Request(
                requester_id=ids["requester"],
                folio=f"SIG-{uuid.uuid4().hex[:6]}",
                title="Sin red",
                description="Sin red",
                physical_location="Aula 1",
                channel=RequestChannel.PORTAL,
                status=status,
                priority=Priority.P2,
                service_level_version_id=ids["version"] if con_acuerdo else None,
                created_at=INICIO,
            )
            for inicio, fin in pausas:
                request.sla_pauses.append(
                    RequestSlaPause(
                        reason="external_input",
                        started_by_id=ids["requester"],
                        started_at=_min(inicio),
                        ended_at=_min(fin) if fin is not None else None,
                    )
                )
            session.add(request)
            await session.commit()
            return request.id

    return asyncio.run(crear())


def _detectar(maker, ahora: datetime) -> list[uuid.UUID]:
    async def correr() -> list[uuid.UUID]:
        async with maker() as session:
            return [r.id for r in await SlaMonitorService(session).detectar_en_riesgo(ahora)]

    return asyncio.run(correr())


def _alertada_en(maker, request_id: uuid.UUID) -> datetime | None:
    async def leer() -> datetime | None:
        async with maker() as session:
            request = await session.get(Request, request_id)
            return request.sla_risk_alerted_at

    return asyncio.run(leer())


# --- detección -----------------------------------------------------------------


def test_al_79_por_ciento_no_se_detecta(entorno) -> None:
    maker, ids = entorno
    _crear(maker, ids)

    assert _detectar(maker, _min(79)) == []


def test_al_80_por_ciento_se_detecta(entorno) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids)

    assert _detectar(maker, _min(80)) == [request_id]


def test_el_tiempo_en_espera_no_cuenta(entorno) -> None:
    maker, ids = entorno
    # 30 minutos en «En espera»: a los 100 min transcurridos solo van 70 efectivos.
    request_id = _crear(maker, ids, pausas=((20, 50),))

    assert _detectar(maker, _min(100)) == []
    assert _detectar(maker, _min(110)) == [request_id]


def test_una_espera_abierta_congela_el_reloj(entorno) -> None:
    maker, ids = entorno
    _crear(maker, ids, status=RequestStatus.WAITING, pausas=((50, None),))

    assert _detectar(maker, _min(500)) == []


@pytest.mark.parametrize(
    "estado",
    [RequestStatus.RESOLVED, RequestStatus.CLOSED, RequestStatus.CLOSED_UNVERIFIED],
)
def test_las_solicitudes_cerradas_no_se_detectan(entorno, estado) -> None:
    maker, ids = entorno
    _crear(maker, ids, status=estado)

    assert _detectar(maker, _min(95)) == []


def test_sin_version_de_acuerdo_no_se_detecta(entorno) -> None:
    maker, ids = entorno
    _crear(maker, ids, con_acuerdo=False)

    assert _detectar(maker, _min(95)) == []


# --- marcado e idempotencia ----------------------------------------------------


def test_una_solicitud_ya_alertada_no_se_vuelve_a_detectar(entorno) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids)

    async def vuelta(ahora: datetime) -> list[uuid.UUID]:
        async with maker() as session:
            return [r.id for r in await SlaMonitorService(session).ejecutar_vuelta(ahora)]

    assert asyncio.run(vuelta(_min(80))) == [request_id]
    assert asyncio.run(vuelta(_min(81))) == []
    assert _detectar(maker, _min(95)) == []


def test_marcar_alertada_no_confirma_la_transaccion(entorno) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids)

    async def marcar() -> datetime | None:
        async with maker() as session:
            request = await SlaMonitorService(session).marcar_alertada(request_id, _min(80))
            return request.sla_risk_alerted_at

    assert asyncio.run(marcar()) is not None
    # La sesión se cerró sin commit: el cambio no quedó guardado.
    assert _alertada_en(maker, request_id) is None


def test_marcar_alertada_falla_si_la_solicitud_no_existe(entorno) -> None:
    maker, _ids = entorno

    async def marcar() -> None:
        async with maker() as session:
            await SlaMonitorService(session).marcar_alertada(uuid.uuid4(), _min(80))

    with pytest.raises(SolicitudNoEncontradaError):
        asyncio.run(marcar())


def test_ejecutar_vuelta_marca_avisa_y_confirma(entorno) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids)
    _crear(maker, ids, con_acuerdo=False)
    recibidas: list[uuid.UUID] = []

    async def al_detectar(_session, solicitudes) -> None:
        recibidas.extend(r.id for r in solicitudes)

    async def vuelta() -> None:
        async with maker() as session:
            await SlaMonitorService(session).ejecutar_vuelta(_min(85), al_detectar=al_detectar)

    asyncio.run(vuelta())

    assert recibidas == [request_id]
    assert _alertada_en(maker, request_id) is not None


def test_si_el_aviso_falla_la_vuelta_no_marca_nada(entorno) -> None:
    maker, ids = entorno
    request_id = _crear(maker, ids)

    async def al_detectar(_session, _solicitudes) -> None:
        raise RuntimeError("fallo al avisar")

    async def vuelta() -> None:
        async with maker() as session:
            await SlaMonitorService(session).ejecutar_vuelta(_min(85), al_detectar=al_detectar)

    with pytest.raises(RuntimeError):
        asyncio.run(vuelta())

    assert _alertada_en(maker, request_id) is None
    assert _detectar(maker, _min(85)) == [request_id]


def test_el_aviso_por_defecto_registra_en_el_log(entorno, caplog) -> None:
    maker, ids = entorno
    _crear(maker, ids)

    async def vuelta() -> None:
        async with maker() as session:
            await SlaMonitorService(session).ejecutar_vuelta(_min(90))

    with caplog.at_level(logging.WARNING, logger="sigpi.sla_monitor"):
        asyncio.run(vuelta())

    assert any(r.getMessage() == "sla_en_riesgo_detectada" for r in caplog.records)


# --- bucle ---------------------------------------------------------------------


def test_el_bucle_registra_el_error_y_sigue(entorno, caplog) -> None:
    maker, _ids = entorno
    llamadas = 0

    class Detener(BaseException):
        """Sale del bucle sin que el manejo de errores de una vuelta la atrape."""

    def fabrica():
        nonlocal llamadas
        llamadas += 1
        if llamadas == 1:
            raise RuntimeError("base de datos caída")
        if llamadas == 3:
            raise Detener
        return maker()

    with caplog.at_level(logging.ERROR, logger="sigpi.sla_monitor"), pytest.raises(Detener):
        asyncio.run(ejecutar_monitor(fabrica, 0))

    assert llamadas == 3
    assert [r.getMessage() for r in caplog.records] == ["sla_monitor_vuelta_fallida"]


def test_con_el_monitor_deshabilitado_no_arranca_ningun_bucle(monkeypatch) -> None:
    llamadas: list[float] = []

    async def falso(_factory, intervalo, *_args, **_kwargs) -> None:
        llamadas.append(intervalo)

    monkeypatch.setattr(settings, "sla_monitor_enabled", False)
    monkeypatch.setattr(main_module, "ejecutar_monitor", falso)

    with TestClient(main_module.app) as client:
        assert client.get("/health").status_code == 200

    assert llamadas == []


def test_con_el_monitor_habilitado_arranca_y_se_detiene_al_apagar(monkeypatch) -> None:
    eventos: list[str] = []

    async def falso(_factory, intervalo, *_args, **_kwargs) -> None:
        eventos.append(f"inicio:{intervalo}")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            eventos.append("cancelado")
            raise

    monkeypatch.setattr(settings, "sla_monitor_enabled", True)
    monkeypatch.setattr(settings, "sla_monitor_interval_seconds", 30)
    monkeypatch.setattr(main_module, "ejecutar_monitor", falso)

    with TestClient(main_module.app) as client:
        assert client.get("/health").status_code == 200

    assert eventos == ["inicio:30", "cancelado"]


def test_la_configuracion_por_defecto_deja_el_monitor_apagado() -> None:
    campos = Settings.model_fields

    assert campos["sla_monitor_enabled"].default is False
    assert campos["sla_monitor_interval_seconds"].default == 30
