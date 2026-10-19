"""Pruebas del servicio de seguimiento y resolución (S3-12, HU-04.1)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.enums import RequestChannel, RequestStatus, UserType, WaitReason
from app.models.identity import User
from app.models.request import Request, RequestSlaPause
from app.services.seguimiento_service import SeguimientoService
from app.services.sla_clock_service import EstadoInvalidoError, SolicitudNoEncontradaError

AHORA = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def _user(user_id: uuid.UUID, institutional_id: str) -> User:
    return User(
        id=user_id,
        institutional_id=institutional_id,
        full_name=f"Usuario {institutional_id}",
        email=f"{institutional_id}@example.test",
        user_type=UserType.ACADEMIC,
        is_active=True,
    )


@pytest.fixture
def db():
    """Base SQLite en memoria con un técnico y un solicitante."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"technician": uuid.uuid4(), "requester": uuid.uuid4()}

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            session.add_all(
                [_user(ids["technician"], "tec-001"), _user(ids["requester"], "req-001")]
            )
            await session.commit()

    asyncio.run(prepare())
    try:
        yield maker, ids
    finally:
        asyncio.run(engine.dispose())


def _seed_request(maker, ids, status, created_at=None, pauses=()) -> uuid.UUID:
    """Crea una solicitud en el estado dado, con periodos de espera (inicio, fin) opcionales."""

    async def run() -> uuid.UUID:
        async with maker() as session:
            request = Request(
                requester_id=ids["requester"],
                folio=f"SIG-{uuid.uuid4().hex[:6]}",
                title="Sin red",
                description="El laboratorio perdió conectividad.",
                physical_location="Edificio A",
                channel=RequestChannel.PORTAL,
                status=status,
                created_at=created_at or AHORA,
            )
            session.add(request)
            await session.flush()
            for started_at, ended_at in pauses:
                session.add(
                    RequestSlaPause(
                        request_id=request.id,
                        reason=WaitReason.EXTERNAL_INPUT,
                        started_by_id=ids["technician"],
                        started_at=started_at,
                        ended_at=ended_at,
                    )
                )
            await session.commit()
            return request.id

    return asyncio.run(run())


def _call(maker, method: str, *args, **kwargs):
    """Ejecuta un método del servicio en su propia sesión."""

    async def run():
        async with maker() as session:
            return await getattr(SeguimientoService(session), method)(*args, **kwargs)

    return asyncio.run(run())


# --- Iniciar la atención -----------------------------------------------------------


def test_iniciar_atencion_marca_primera_respuesta_y_deja_bitacora(db) -> None:
    maker, ids = db
    request_id = _seed_request(maker, ids, RequestStatus.ASSIGNED)

    request = _call(maker, "iniciar_atencion", request_id, ids["technician"], ahora=AHORA)

    assert request.status == RequestStatus.IN_PROGRESS
    assert request.first_response_at is not None
    (entry,) = request.logs
    assert entry.author_id == ids["technician"]
    assert entry.previous_status == RequestStatus.ASSIGNED
    assert entry.new_status == RequestStatus.IN_PROGRESS


@pytest.mark.parametrize(
    "status",
    [RequestStatus.REGISTERED, RequestStatus.PENDING_VERIFICATION, RequestStatus.IN_PROGRESS],
)
def test_no_se_puede_iniciar_desde_otros_estados(db, status: RequestStatus) -> None:
    maker, ids = db
    request_id = _seed_request(maker, ids, status)

    with pytest.raises(EstadoInvalidoError):
        _call(maker, "iniciar_atencion", request_id, ids["technician"])


# --- Diagnóstico -------------------------------------------------------------------


def test_el_diagnostico_se_actualiza_y_el_historial_se_conserva(db) -> None:
    maker, ids = db
    request_id = _seed_request(maker, ids, RequestStatus.ASSIGNED)

    _call(maker, "registrar_diagnostico", request_id, ids["technician"], "Cable dañado")
    request = _call(
        maker, "registrar_diagnostico", request_id, ids["technician"], "Puerto averiado"
    )

    assert request.diagnosis == "Puerto averiado"
    bitacora = _call(maker, "listar_bitacora", request_id)
    assert [e.action for e in bitacora] == ["Diagnóstico registrado", "Diagnóstico actualizado"]
    assert [e.notes for e in bitacora] == ["Cable dañado", "Puerto averiado"]


def test_no_se_registra_diagnostico_en_una_solicitud_sin_atender(db) -> None:
    maker, ids = db
    request_id = _seed_request(maker, ids, RequestStatus.REGISTERED)

    with pytest.raises(EstadoInvalidoError):
        _call(maker, "registrar_diagnostico", request_id, ids["technician"], "Cable dañado")


# --- Resolución --------------------------------------------------------------------


def test_resolver_calcula_el_tiempo_sin_contar_las_esperas(db) -> None:
    maker, ids = db
    # 120 min desde el alta, de los cuales 30 estuvo en espera: 90 min efectivos.
    request_id = _seed_request(
        maker,
        ids,
        RequestStatus.IN_PROGRESS,
        created_at=AHORA - timedelta(minutes=120),
        pauses=[(AHORA - timedelta(minutes=90), AHORA - timedelta(minutes=60))],
    )

    request = _call(
        maker, "resolver", request_id, ids["technician"], "Se reemplazó el cable", ahora=AHORA
    )

    assert request.status == RequestStatus.RESOLVED
    assert request.solution == "Se reemplazó el cable"
    assert request.resolved_at is not None
    assert request.resolution_minutes == 90
    (entry,) = request.logs
    assert entry.previous_status == RequestStatus.IN_PROGRESS
    assert entry.new_status == RequestStatus.RESOLVED
    assert "90 min" in entry.notes
    assert "confirmar la solución" in entry.notes


def test_resolver_puede_registrar_el_diagnostico_en_la_misma_llamada(db) -> None:
    maker, ids = db
    request_id = _seed_request(maker, ids, RequestStatus.ASSIGNED)

    request = _call(
        maker,
        "resolver",
        request_id,
        ids["technician"],
        "Se reinició el equipo",
        diagnosis="Servicio colgado",
        ahora=AHORA,
    )

    assert request.diagnosis == "Servicio colgado"
    assert request.first_response_at is not None


@pytest.mark.parametrize(
    "status",
    [
        RequestStatus.REGISTERED,
        RequestStatus.PENDING_VERIFICATION,
        RequestStatus.WAITING,
        RequestStatus.RESOLVED,
        RequestStatus.CLOSED,
    ],
)
def test_no_se_puede_resolver_desde_otros_estados(db, status: RequestStatus) -> None:
    maker, ids = db
    request_id = _seed_request(maker, ids, status)

    with pytest.raises(EstadoInvalidoError):
        _call(maker, "resolver", request_id, ids["technician"], "Solución")


# --- Solicitud inexistente ---------------------------------------------------------


def test_una_solicitud_inexistente_se_reporta(db) -> None:
    maker, ids = db

    with pytest.raises(SolicitudNoEncontradaError):
        _call(maker, "iniciar_atencion", uuid.uuid4(), ids["technician"])
    with pytest.raises(SolicitudNoEncontradaError):
        _call(maker, "listar_bitacora", uuid.uuid4())
