"""Pruebas del servicio de acuerdos de nivel de servicio versionados (S2-15, HU-08.1).

Usan el servicio y el repositorio reales contra una base de datos SQLite en
memoria. Cubren los tres criterios de aceptación: versión nueva con histórico
(AC1), inconsistencia entre tiempos (AC2) y combinación sin acuerdo (AC3).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.db.base import Base
from app.models.catalog import AreaServicio, Categoria
from app.models.enums import Priority
from app.models.organization import OrganizationalUnit
from app.repositories.sla_repository import SlaRepository
from app.schemas.sla import SlaAgreementCreate, SlaPriorityTimes, SlaVersionCreate
from app.services.sla_service import (
    SlaConflictError,
    SlaNotConfiguredError,
    SlaNotFoundError,
    SlaService,
    SlaValidationError,
)

T0 = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
    await engine.dispose()


@pytest_asyncio.fixture
async def service(session: AsyncSession) -> SlaService:
    return SlaService(SlaRepository(session))


@pytest_asyncio.fixture
async def category_id(session: AsyncSession) -> uuid.UUID:
    unit = OrganizationalUnit(name="DTIC", unit_type="department")
    session.add(unit)
    await session.flush()
    area = AreaServicio(unit_id=unit.id, name="Redes")
    session.add(area)
    await session.flush()
    category = Categoria(area_id=area.id, name="Conectividad")
    session.add(category)
    await session.commit()
    return category.id


def _times(priority: Priority, first: int, resolution: int) -> SlaPriorityTimes:
    return SlaPriorityTimes(
        priority=priority, first_response_minutes=first, resolution_minutes=resolution
    )


def _version(valid_from: datetime, *times: SlaPriorityTimes) -> SlaVersionCreate:
    return SlaVersionCreate(valid_from=valid_from, times=list(times))


async def _agreement(service: SlaService, category: uuid.UUID | None = None):
    if category is None:
        return await service.create_agreement(
            SlaAgreementCreate(name="Predeterminado", is_default=True)
        )
    return await service.create_agreement(
        SlaAgreementCreate(name="Conectividad", category_id=category)
    )


# --- acuerdos -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_crear_acuerdo_de_categoria(service, category_id) -> None:
    agreement = await _agreement(service, category_id)

    assert agreement.category_id == category_id
    assert agreement.is_default is False
    assert agreement.is_active is True


@pytest.mark.asyncio
async def test_no_permite_dos_acuerdos_activos_para_la_misma_categoria(
    service, category_id
) -> None:
    await _agreement(service, category_id)

    with pytest.raises(SlaConflictError):
        await _agreement(service, category_id)


@pytest.mark.asyncio
async def test_no_permite_dos_acuerdos_predeterminados(service) -> None:
    await _agreement(service)

    with pytest.raises(SlaConflictError):
        await _agreement(service)


@pytest.mark.asyncio
async def test_acuerdo_de_categoria_inexistente_se_rechaza(service) -> None:
    with pytest.raises(SlaValidationError):
        await service.create_agreement(SlaAgreementCreate(name="X", category_id=uuid.uuid4()))


def test_acuerdo_predeterminado_no_lleva_categoria() -> None:
    with pytest.raises(ValidationError):
        SlaAgreementCreate(name="X", is_default=True, category_id=uuid.uuid4())


def test_acuerdo_que_no_es_predeterminado_requiere_categoria() -> None:
    with pytest.raises(ValidationError):
        SlaAgreementCreate(name="X")


# --- AC1: versión nueva con histórico ---------------------------------------
@pytest.mark.asyncio
async def test_primera_version_queda_vigente_sin_fecha_de_termino(service, category_id) -> None:
    agreement = await _agreement(service, category_id)

    created = await service.publish_version(
        agreement.id, _version(T0, _times(Priority.P1, 15, 120), _times(Priority.P2, 30, 240))
    )

    assert [v.version for v in created] == [1, 1]
    assert all(v.valid_to is None for v in created)


@pytest.mark.asyncio
async def test_version_nueva_conserva_el_historico_y_cierra_la_anterior(
    service, category_id
) -> None:
    agreement = await _agreement(service, category_id)
    await service.publish_version(agreement.id, _version(T0, _times(Priority.P1, 15, 120)))

    await service.publish_version(agreement.id, _version(T1, _times(Priority.P1, 10, 60)))

    history = await service.list_versions(agreement.id, priority=Priority.P1)
    assert [v.version for v in history] == [2, 1]
    assert history[0].valid_to is None
    assert history[1].valid_to is not None
    assert history[1].first_response_minutes == 15
    assert history[1].resolution_minutes == 120


@pytest.mark.asyncio
async def test_solicitud_en_curso_conserva_el_acuerdo_con_el_que_se_registro(
    service, category_id
) -> None:
    agreement = await _agreement(service, category_id)
    await service.publish_version(agreement.id, _version(T0, _times(Priority.P1, 15, 120)))
    await service.publish_version(agreement.id, _version(T1, _times(Priority.P1, 10, 60)))

    antes = await service.resolve_effective(category_id, Priority.P1, T0 + timedelta(days=5))
    despues = await service.resolve_effective(category_id, Priority.P1, T1 + timedelta(days=1))

    assert (antes.version, antes.resolution_minutes) == (1, 120)
    assert (despues.version, despues.resolution_minutes) == (2, 60)
    assert antes.used_default is False


@pytest.mark.asyncio
async def test_version_nueva_solo_cierra_las_prioridades_que_modifica(service, category_id) -> None:
    agreement = await _agreement(service, category_id)
    await service.publish_version(
        agreement.id, _version(T0, _times(Priority.P1, 15, 120), _times(Priority.P2, 30, 240))
    )

    await service.publish_version(agreement.id, _version(T1, _times(Priority.P1, 10, 60)))

    p2 = await service.resolve_effective(category_id, Priority.P2, T1 + timedelta(days=1))
    assert (p2.version, p2.resolution_minutes) == (1, 240)


@pytest.mark.asyncio
async def test_fecha_de_vigencia_no_puede_ser_anterior_a_la_version_vigente(
    service, category_id
) -> None:
    agreement = await _agreement(service, category_id)
    await service.publish_version(agreement.id, _version(T1, _times(Priority.P1, 15, 120)))

    with pytest.raises(SlaValidationError):
        await service.publish_version(agreement.id, _version(T0, _times(Priority.P1, 10, 60)))


@pytest.mark.asyncio
async def test_version_de_acuerdo_inexistente_responde_no_encontrado(service) -> None:
    with pytest.raises(SlaNotFoundError):
        await service.publish_version(uuid.uuid4(), _version(T0, _times(Priority.P1, 15, 120)))


# --- AC2: inconsistencia entre tiempos --------------------------------------
@pytest.mark.parametrize("first, resolution", [(60, 60), (60, 30)])
def test_resolucion_menor_o_igual_a_primera_respuesta_se_rechaza(first, resolution) -> None:
    with pytest.raises(ValidationError, match="Inconsistencia"):
        _times(Priority.P1, first, resolution)


def test_tiempos_no_positivos_se_rechazan() -> None:
    with pytest.raises(ValidationError):
        _times(Priority.P1, 0, 60)


def test_una_prioridad_no_puede_repetirse_en_la_misma_version() -> None:
    with pytest.raises(ValidationError):
        _version(T0, _times(Priority.P1, 15, 120), _times(Priority.P1, 10, 60))


@pytest.mark.asyncio
async def test_inconsistencia_no_guarda_ninguna_version(service, category_id) -> None:
    agreement = await _agreement(service, category_id)

    with pytest.raises(ValidationError):
        _version(T0, _times(Priority.P1, 15, 120), _times(Priority.P2, 90, 90))

    assert await service.list_versions(agreement.id) == []


# --- AC3: combinación sin acuerdo -> predeterminado ------------------------
@pytest.mark.asyncio
async def test_combinacion_sin_acuerdo_aplica_el_predeterminado_y_avisa(
    service, category_id
) -> None:
    default = await _agreement(service)
    await service.publish_version(default.id, _version(T0, _times(Priority.P3, 60, 480)))
    own = await _agreement(service, category_id)
    await service.publish_version(own.id, _version(T0, _times(Priority.P1, 15, 120)))

    result = await service.resolve_effective(category_id, Priority.P3, T0 + timedelta(days=1))

    assert result.used_default is True
    assert result.agreement_id == default.id
    assert result.resolution_minutes == 480
    assert result.notice is not None
    assert "P3" in result.notice


@pytest.mark.asyncio
async def test_categoria_sin_acuerdo_propio_usa_el_predeterminado(service, category_id) -> None:
    default = await _agreement(service)
    await service.publish_version(default.id, _version(T0, _times(Priority.P2, 30, 240)))

    result = await service.resolve_effective(category_id, Priority.P2, T0 + timedelta(days=1))

    assert result.used_default is True
    assert result.notice is not None


@pytest.mark.asyncio
async def test_sin_acuerdo_propio_ni_predeterminado_falla(service, category_id) -> None:
    with pytest.raises(SlaNotConfiguredError):
        await service.resolve_effective(category_id, Priority.P1, T0)


@pytest.mark.asyncio
async def test_antes_de_la_entrada_en_vigor_no_hay_acuerdo(service, category_id) -> None:
    agreement = await _agreement(service, category_id)
    await service.publish_version(agreement.id, _version(T1, _times(Priority.P1, 15, 120)))

    with pytest.raises(SlaNotConfiguredError):
        await service.resolve_effective(category_id, Priority.P1, T0)


@pytest.mark.asyncio
async def test_fechas_sin_zona_horaria_se_interpretan_como_utc(service, category_id) -> None:
    agreement = await _agreement(service, category_id)
    await service.publish_version(agreement.id, _version(T0, _times(Priority.P1, 15, 120)))

    result = await service.resolve_effective(
        category_id, Priority.P1, (T0 + timedelta(days=1)).replace(tzinfo=None)
    )

    assert result.version == 1
