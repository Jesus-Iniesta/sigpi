"""Pruebas de la suspensión y reanudación del reloj del SLA (S3-17, HU-04.2)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.dependencies import get_current_user
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.enums import RequestChannel, RequestStatus, UserType, WaitReason
from app.models.identity import User
from app.models.request import Request
from app.services.sla_clock_service import (
    EstadoInvalidoError,
    SlaClockService,
    SolicitudNoEncontradaError,
    minutos_efectivos,
    minutos_restantes,
    minutos_suspendidos,
)

INICIO = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _minutos(n: int) -> timedelta:
    return timedelta(minutes=n)


@pytest.fixture
def entorno():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"requester": uuid.uuid4(), "tecnico": uuid.uuid4()}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            for key, user_type in (
                ("requester", UserType.ACADEMIC),
                ("tecnico", UserType.TECHNICAL),
            ):
                uid = ids[key]
                session.add(
                    User(
                        id=uid,
                        institutional_id=f"u-{uid.hex[:8]}",
                        full_name=key,
                        email=f"{uid.hex[:8]}@example.test",
                        user_type=user_type,
                        is_active=True,
                    )
                )
            await session.commit()

    asyncio.run(preparar())
    try:
        yield maker, ids
    finally:
        asyncio.run(engine.dispose())


async def _crear(maker, ids, status: RequestStatus = RequestStatus.IN_PROGRESS) -> uuid.UUID:
    async with maker() as session:
        request = Request(
            requester_id=ids["requester"],
            folio=f"SIG-{uuid.uuid4().hex[:6]}",
            title="Sin red",
            description="Sin red",
            physical_location="Aula 1",
            channel=RequestChannel.PORTAL,
            status=status,
            created_at=INICIO,
        )
        session.add(request)
        await session.commit()
        return request.id


def _ejecutar(maker, ids, escenario):
    async def correr():
        async with maker() as session:
            return await escenario(SlaClockService(session), session)

    return asyncio.run(correr())


def test_suspender_cambia_el_estado_y_registra_motivo_y_bitacora(entorno) -> None:
    maker, ids = entorno
    request_id = asyncio.run(_crear(maker, ids))

    async def escenario(servicio, _session):
        return await servicio.suspender(
            request_id,
            ids["tecnico"],
            WaitReason.USER_INFORMATION,
            "Falta el número de serie",
            ahora=INICIO + _minutos(30),
        )

    request = _ejecutar(maker, ids, escenario)

    assert request.status == RequestStatus.WAITING
    assert len(request.sla_pauses) == 1
    pausa = request.sla_pauses[0]
    assert pausa.reason == WaitReason.USER_INFORMATION
    assert pausa.ended_at is None
    assert [log.action for log in request.logs] == ["Reloj del SLA suspendido"]
    assert "Falta el número de serie" in request.logs[0].notes


def test_reanudar_cierra_la_pausa_y_regresa_a_en_progreso(entorno) -> None:
    maker, ids = entorno
    request_id = asyncio.run(_crear(maker, ids))

    async def escenario(servicio, _session):
        await servicio.suspender(
            request_id, ids["tecnico"], WaitReason.EXTERNAL_INPUT, ahora=INICIO + _minutos(30)
        )
        return await servicio.reanudar(request_id, ids["tecnico"], ahora=INICIO + _minutos(90))

    request = _ejecutar(maker, ids, escenario)

    assert request.status == RequestStatus.IN_PROGRESS
    assert request.sla_pauses[0].ended_at is not None
    assert [log.action for log in request.logs] == [
        "Reloj del SLA suspendido",
        "Reloj del SLA reanudado",
    ]


def test_el_periodo_suspendido_se_descuenta_del_tiempo_efectivo(entorno) -> None:
    maker, ids = entorno
    request_id = asyncio.run(_crear(maker, ids))

    async def escenario(servicio, _session):
        await servicio.suspender(
            request_id, ids["tecnico"], WaitReason.EXTERNAL_INPUT, ahora=INICIO + _minutos(30)
        )
        return await servicio.reanudar(request_id, ids["tecnico"], ahora=INICIO + _minutos(90))

    request = _ejecutar(maker, ids, escenario)
    ahora = INICIO + _minutos(120)

    assert minutos_suspendidos(request, ahora) == pytest.approx(60)
    assert minutos_efectivos(request, ahora) == pytest.approx(60)
    assert minutos_restantes(request, 240, ahora) == pytest.approx(180)


def test_una_espera_abierta_cuenta_hasta_el_momento_de_consulta(entorno) -> None:
    maker, ids = entorno
    request_id = asyncio.run(_crear(maker, ids))

    async def escenario(servicio, _session):
        return await servicio.suspender(
            request_id, ids["tecnico"], WaitReason.EXTERNAL_INPUT, ahora=INICIO + _minutos(30)
        )

    request = _ejecutar(maker, ids, escenario)

    # Mientras sigue en espera, el tiempo efectivo se queda congelado en 30 min.
    assert minutos_efectivos(request, INICIO + _minutos(60)) == pytest.approx(30)
    assert minutos_efectivos(request, INICIO + _minutos(600)) == pytest.approx(30)


def test_varias_esperas_se_acumulan(entorno) -> None:
    maker, ids = entorno
    request_id = asyncio.run(_crear(maker, ids))

    async def escenario(servicio, _session):
        for inicio, fin in ((10, 20), (40, 70)):
            await servicio.suspender(
                request_id,
                ids["tecnico"],
                WaitReason.EXTERNAL_INPUT,
                ahora=INICIO + _minutos(inicio),
            )
            request = await servicio.reanudar(
                request_id, ids["tecnico"], ahora=INICIO + _minutos(fin)
            )
        return request

    request = _ejecutar(maker, ids, escenario)

    assert len(request.sla_pauses) == 2
    assert minutos_suspendidos(request, INICIO + _minutos(100)) == pytest.approx(40)
    assert minutos_efectivos(request, INICIO + _minutos(100)) == pytest.approx(60)


@pytest.mark.parametrize(
    "estado",
    [
        RequestStatus.REGISTERED,
        RequestStatus.WAITING,
        RequestStatus.RESOLVED,
        RequestStatus.CLOSED,
    ],
)
def test_no_se_puede_suspender_desde_un_estado_no_permitido(entorno, estado) -> None:
    maker, ids = entorno
    request_id = asyncio.run(_crear(maker, ids, estado))

    async def escenario(servicio, _session):
        await servicio.suspender(request_id, ids["tecnico"], WaitReason.EXTERNAL_INPUT)

    with pytest.raises(EstadoInvalidoError):
        _ejecutar(maker, ids, escenario)


def test_no_se_puede_reanudar_una_solicitud_que_no_esta_en_espera(entorno) -> None:
    maker, ids = entorno
    request_id = asyncio.run(_crear(maker, ids))

    async def escenario(servicio, _session):
        await servicio.reanudar(request_id, ids["tecnico"])

    with pytest.raises(EstadoInvalidoError):
        _ejecutar(maker, ids, escenario)


def test_suspender_una_solicitud_inexistente_falla(entorno) -> None:
    maker, ids = entorno

    async def escenario(servicio, _session):
        await servicio.suspender(uuid.uuid4(), ids["tecnico"], WaitReason.EXTERNAL_INPUT)

    with pytest.raises(SolicitudNoEncontradaError):
        _ejecutar(maker, ids, escenario)


# --- endpoints -----------------------------------------------------------------


@pytest.fixture
def cliente(entorno):
    maker, ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    agente = SimpleNamespace(
        id=ids["tecnico"],
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name="support_agent"))],
    )
    fastapi_app.dependency_overrides[get_session] = sesion
    fastapi_app.dependency_overrides[get_current_user] = lambda: agente
    try:
        yield TestClient(fastapi_app), maker, ids
    finally:
        fastapi_app.dependency_overrides.clear()


def test_endpoint_espera_y_reanudar(cliente) -> None:
    client, maker, ids = cliente
    request_id = asyncio.run(_crear(maker, ids))

    en_espera = client.post(
        f"/solicitudes/{request_id}/espera",
        json={"reason": "user_information", "detail": "Falta el número de serie"},
    )
    reanudada = client.post(f"/solicitudes/{request_id}/reanudar")

    assert en_espera.status_code == 200, en_espera.text
    assert en_espera.json()["status"] == "waiting"
    assert reanudada.status_code == 200, reanudada.text
    assert reanudada.json()["status"] == "in_progress"


def test_endpoint_responde_409_si_el_estado_no_lo_permite(cliente) -> None:
    client, maker, ids = cliente
    request_id = asyncio.run(_crear(maker, ids, RequestStatus.REGISTERED))

    espera = client.post(f"/solicitudes/{request_id}/espera", json={"reason": "external_input"})
    reanudar = client.post(f"/solicitudes/{request_id}/reanudar")

    assert espera.status_code == 409
    assert reanudar.status_code == 409


def test_endpoint_responde_404_si_la_solicitud_no_existe(cliente) -> None:
    client, _maker, _ids = cliente

    respuesta = client.post(
        f"/solicitudes/{uuid.uuid4()}/espera", json={"reason": "external_input"}
    )

    assert respuesta.status_code == 404


def test_endpoint_rechaza_un_motivo_desconocido(cliente) -> None:
    client, maker, ids = cliente
    request_id = asyncio.run(_crear(maker, ids))

    respuesta = client.post(f"/solicitudes/{request_id}/espera", json={"reason": "porque_si"})

    assert respuesta.status_code == 422


def test_endpoint_exige_iniciar_sesion() -> None:
    cliente_sin_sesion = TestClient(fastapi_app)

    respuesta = cliente_sin_sesion.post(
        f"/solicitudes/{uuid.uuid4()}/espera", json={"reason": "external_input"}
    )

    assert respuesta.status_code == 401
