"""Idempotencia de las semillas del catálogo predefinido (COR-04).

Usa SQLite en memoria con los modelos reales: ejecutar las semillas dos veces no
debe duplicar unidades, áreas, categorías, especialidades ni turnos.
"""

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.db.base import Base
from app.domain.catalog_options import (
    CATEGORY_OPTIONS,
    SERVICE_AREA_OPTIONS,
    SHIFT_OPTIONS,
    SPECIALTY_OPTIONS,
)
from app.models.catalog import AreaServicio, Categoria, Especialidad, Turno
from app.models.organization import OrganizationalUnit
from app.seeds import service


@pytest_asyncio.fixture
async def maker(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(service, "_session_factory", lambda: session_maker)
    try:
        yield session_maker
    finally:
        await engine.dispose()


async def _run_catalog_seeds() -> None:
    await service.run_seed_organizational_units()
    await service.run_seed_area()
    await service.run_seed_categories()
    await service.run_seed_service_areas()
    await service.run_seed_specialties()
    await service.run_seed_shifts()


async def _count(maker, model) -> int:
    async with maker() as session:
        return await session.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_semillas_del_catalogo_no_duplican_al_ejecutarse_dos_veces(maker) -> None:
    await _run_catalog_seeds()
    first = {
        model: await _count(maker, model)
        for model in (AreaServicio, Categoria, Especialidad, Turno, OrganizationalUnit)
    }

    await _run_catalog_seeds()
    second = {
        model: await _count(maker, model)
        for model in (AreaServicio, Categoria, Especialidad, Turno, OrganizationalUnit)
    }

    assert first == second
    # «Soporte técnico» (área heredada de las semillas) + las 4 áreas predefinidas.
    assert second[AreaServicio] == 1 + len(SERVICE_AREA_OPTIONS)
    assert second[Categoria] == len(CATEGORY_OPTIONS)
    assert second[Especialidad] == sum(len(names) for names in SPECIALTY_OPTIONS.values())
    assert second[Turno] == len(SHIFT_OPTIONS)


@pytest.mark.asyncio
async def test_semilla_de_turnos_usa_el_horario_fijo(maker) -> None:
    assert await service.run_seed_shifts() == len(SHIFT_OPTIONS)
    assert await service.run_seed_shifts() == 0

    async with maker() as session:
        matutino = await session.scalar(select(Turno).where(Turno.name == "Matutino"))
    assert (matutino.start_minute, matutino.end_minute) == (7 * 60, 15 * 60)


@pytest.mark.asyncio
async def test_semilla_de_especialidades_requiere_categorias(maker) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        await service.run_seed_specialties()


@pytest.mark.asyncio
async def test_semilla_de_areas_requiere_unidad(maker) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        await service.run_seed_service_areas()
