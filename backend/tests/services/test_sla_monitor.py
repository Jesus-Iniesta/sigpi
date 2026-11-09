"""Pruebas del monitor del umbral de riesgo del SLA (S4-08, HU-07.2)."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.main as main_module
import app.models  # noqa: F401
from app.core.config import Settings, settings
from app.core.permissions import RoleName
from app.db.base import Base
from app.models.enums import Priority, RequestChannel, RequestStatus, UserType
from app.models.identity import Role, User, UserRole
from app.models.notification import Notification
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


# --- umbral de alerta con reloj controlado (S4-10) -----------------------------
#
# Las vueltas del monitor se simulan llamando a `ejecutar_vuelta(ahora)` cada
# `settings.sla_monitor_interval_seconds`, sin `sleep`: el reloj lo fija la prueba.
# Las vueltas arrancan desfasadas del alta para que el cruce del 80 % caiga entre dos.

# Tiempos de resolución supuestos por prioridad (el sprint no fija un catálogo real).
RESOLUCION_POR_PRIORIDAD = {
    Priority.P1: 240,
    Priority.P2: 480,
    Priority.P3: 1440,
    Priority.P4: 2880,
}
DESFASE = timedelta(seconds=7)
MAXIMO_RETRASO = timedelta(seconds=60)
SEGUNDO = timedelta(seconds=1)


def _intervalo() -> timedelta:
    return timedelta(seconds=settings.sla_monitor_interval_seconds)


def _cruce(resolucion: int, pausa: timedelta = timedelta()) -> datetime:
    """Instante exacto en que el tiempo efectivo llega al umbral de riesgo."""
    return INICIO + timedelta(minutes=settings.sla_warning_threshold * resolucion) + pausa


@pytest.fixture
def monitor():
    """Solicitante, un jefe de servicio activo y una versión de acuerdo por prioridad."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"requester": uuid.uuid4(), "jefe": uuid.uuid4()}
    versiones = {prioridad: uuid.uuid4() for prioridad in RESOLUCION_POR_PRIORIDAD}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            for clave in ("requester", "jefe"):
                session.add(
                    User(
                        id=ids[clave],
                        institutional_id=f"u-{ids[clave].hex[:8]}",
                        full_name=clave.title(),
                        email=f"{clave}@example.test",
                        user_type=UserType.ADMINISTRATIVE,
                        is_active=True,
                    )
                )
            rol = Role(name=RoleName.SERVICE_MANAGER)
            session.add(rol)
            acuerdo = ServiceLevelAgreement(name="Acuerdo general", is_default=True)
            session.add(acuerdo)
            await session.flush()
            session.add(UserRole(user_id=ids["jefe"], role_id=rol.id))
            for prioridad, resolucion in RESOLUCION_POR_PRIORIDAD.items():
                session.add(
                    ServiceLevelVersion(
                        id=versiones[prioridad],
                        agreement_id=acuerdo.id,
                        version=1,
                        priority=prioridad,
                        first_response_minutes=30,
                        resolution_minutes=resolucion,
                        valid_from=INICIO - timedelta(days=30),
                    )
                )
            await session.commit()

    asyncio.run(preparar())
    try:
        yield maker, ids, versiones
    finally:
        asyncio.run(engine.dispose())


def _crear_con_prioridad(
    maker,
    ids,
    versiones,
    prioridad: Priority,
    *,
    pausa: tuple[datetime, datetime] | None = None,
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
                status=RequestStatus.IN_PROGRESS,
                priority=prioridad,
                service_level_version_id=versiones[prioridad],
                created_at=INICIO,
            )
            if pausa is not None:
                request.sla_pauses.append(
                    RequestSlaPause(
                        reason="external_input",
                        started_by_id=ids["requester"],
                        started_at=pausa[0],
                        ended_at=pausa[1],
                    )
                )
            session.add(request)
            await session.commit()
            return request.id

    return asyncio.run(crear())


def _vuelta(maker, ahora: datetime) -> list[uuid.UUID]:
    """Una vuelta real del monitor (marca, emite el aviso y confirma) en el instante dado."""

    async def correr() -> list[uuid.UUID]:
        async with maker() as session:
            return [r.id for r in await SlaMonitorService(session).ejecutar_vuelta(ahora)]

    return asyncio.run(correr())


def _vueltas_alrededor(cruce: datetime, antes: int = 3, despues: int = 3) -> list[datetime]:
    """Instantes de las vueltas del monitor cercanas a `cruce`, desfasadas del alta."""
    intervalo = _intervalo()
    previas = (cruce - INICIO - DESFASE) // intervalo
    primera = INICIO + DESFASE + (previas - antes + 1) * intervalo
    return [primera + k * intervalo for k in range(antes + despues)]


def _simular(maker, request_id: uuid.UUID, instantes: list[datetime]) -> datetime | None:
    """Corre las vueltas en orden y devuelve el instante de la que alertó la solicitud."""
    alertada = None
    for ahora in instantes:
        if request_id in _vuelta(maker, ahora):
            assert alertada is None, "la solicitud se alertó en más de una vuelta"
            alertada = ahora
    return alertada


def _avisos(maker, request_id: uuid.UUID) -> int:
    async def contar() -> int:
        async with maker() as session:
            return await session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.request_id == request_id)
            )

    return asyncio.run(contar())


def _resolver(maker, request_id: uuid.UUID) -> None:
    async def resolver() -> None:
        async with maker() as session:
            request = await session.get(Request, request_id)
            request.status = RequestStatus.RESOLVED
            await session.commit()

    asyncio.run(resolver())


@pytest.mark.parametrize("prioridad", list(RESOLUCION_POR_PRIORIDAD))
def test_la_alerta_no_sale_antes_del_80_por_ciento(monitor, prioridad) -> None:
    maker, ids, versiones = monitor
    request_id = _crear_con_prioridad(maker, ids, versiones, prioridad)
    cruce = _cruce(RESOLUCION_POR_PRIORIDAD[prioridad])

    assert _vuelta(maker, cruce - SEGUNDO) == []
    assert _alertada_en(maker, request_id) is None
    assert _avisos(maker, request_id) == 0


@pytest.mark.parametrize("prioridad", list(RESOLUCION_POR_PRIORIDAD))
def test_la_alerta_sale_en_la_primera_vuelta_tras_el_cruce(monitor, prioridad) -> None:
    maker, ids, versiones = monitor
    request_id = _crear_con_prioridad(maker, ids, versiones, prioridad)
    cruce = _cruce(RESOLUCION_POR_PRIORIDAD[prioridad])
    instantes = _vueltas_alrededor(cruce)
    primera_tras_cruce = next(t for t in instantes if t >= cruce)

    alertada = _simular(maker, request_id, instantes)

    assert alertada == primera_tras_cruce
    assert timedelta() <= alertada - cruce <= MAXIMO_RETRASO
    assert alertada - cruce < _intervalo()
    assert _alertada_en(maker, request_id).replace(tzinfo=UTC) == alertada
    assert _avisos(maker, request_id) == 1


def test_una_pausa_desplaza_el_umbral_exactamente_lo_que_duro(monitor) -> None:
    maker, ids, versiones = monitor
    resolucion = RESOLUCION_POR_PRIORIDAD[Priority.P2]
    pausa = timedelta(minutes=17, seconds=23)
    inicio_pausa = _min(60)
    sin_pausa = _crear_con_prioridad(maker, ids, versiones, Priority.P2)
    con_pausa = _crear_con_prioridad(
        maker, ids, versiones, Priority.P2, pausa=(inicio_pausa, inicio_pausa + pausa)
    )
    cruce = _cruce(resolucion)

    assert _detectar(maker, cruce - SEGUNDO) == []
    assert _detectar(maker, cruce) == [sin_pausa]
    assert _detectar(maker, cruce + pausa - SEGUNDO) == [sin_pausa]
    assert _detectar(maker, cruce + pausa) == [sin_pausa, con_pausa]


def test_una_pausa_retrasa_la_alerta_del_monitor_lo_que_duro(monitor) -> None:
    maker, ids, versiones = monitor
    resolucion = RESOLUCION_POR_PRIORIDAD[Priority.P3]
    # Una pausa de 25 intervalos: las vueltas caen en el mismo punto del ciclo.
    pausa = 25 * _intervalo()
    inicio_pausa = _min(120)
    sin_pausa = _crear_con_prioridad(maker, ids, versiones, Priority.P3)
    con_pausa = _crear_con_prioridad(
        maker, ids, versiones, Priority.P3, pausa=(inicio_pausa, inicio_pausa + pausa)
    )

    alerta_sin = _simular(maker, sin_pausa, _vueltas_alrededor(_cruce(resolucion)))
    alerta_con = _simular(maker, con_pausa, _vueltas_alrededor(_cruce(resolucion, pausa)))

    assert alerta_sin is not None and alerta_con is not None
    assert alerta_con - alerta_sin == pausa


def test_una_solicitud_resuelta_antes_del_80_por_ciento_nunca_se_alerta(monitor) -> None:
    maker, ids, versiones = monitor
    resolucion = RESOLUCION_POR_PRIORIDAD[Priority.P1]
    request_id = _crear_con_prioridad(maker, ids, versiones, Priority.P1)
    cruce = _cruce(resolucion)

    assert _vuelta(maker, cruce - timedelta(minutes=10)) == []
    _resolver(maker, request_id)

    for ahora in _vueltas_alrededor(cruce) + [INICIO + timedelta(minutes=10 * resolucion)]:
        assert _vuelta(maker, ahora) == []
    assert _alertada_en(maker, request_id) is None
    assert _avisos(maker, request_id) == 0


def test_dos_vueltas_seguidas_no_duplican_la_alerta(monitor) -> None:
    maker, ids, versiones = monitor
    request_id = _crear_con_prioridad(maker, ids, versiones, Priority.P2)
    primera = _cruce(RESOLUCION_POR_PRIORIDAD[Priority.P2]) + SEGUNDO

    assert _vuelta(maker, primera) == [request_id]
    assert _vuelta(maker, primera + _intervalo()) == []

    assert _alertada_en(maker, request_id).replace(tzinfo=UTC) == primera
    assert _avisos(maker, request_id) == 1


def test_el_intervalo_por_defecto_es_de_a_lo_mas_30_segundos() -> None:
    intervalo = Settings.model_fields["sla_monitor_interval_seconds"].default

    assert 0 < intervalo <= 30
