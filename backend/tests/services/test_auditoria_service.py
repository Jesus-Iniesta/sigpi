"""Tests for the audit change-recording service (S2-08, HU-10.3)."""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.auditoria import Auditoria
from app.repositories.auditoria_repository import AuditoriaRepository
from app.services.auditoria_service import AuditoriaService


@pytest_asyncio.fixture
async def service():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with maker() as session:
        yield AuditoriaService(AuditoriaRepository(session)), session
    await engine.dispose()


@pytest.mark.asyncio
async def test_registra_autor_fecha_y_valores_anterior_nuevo(service) -> None:
    audit_service, session = service
    actor_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    occurred_at = datetime(2026, 10, 4, 20, 0, tzinfo=UTC)

    entry = await audit_service.registrar_cambio(
        actor_id=actor_id,
        action="user.updated",
        entity_type="user",
        entity_id=entity_id,
        old_values={"is_active": True, "max_load": 5},
        new_values={"is_active": False, "max_load": 8},
        ip_address="192.0.2.10",
        created_at=occurred_at,
    )

    assert entry.actor_id == actor_id
    assert entry.entity_id == str(entity_id)
    assert entry.created_at.replace(tzinfo=UTC) == occurred_at
    assert entry.old_values == {"is_active": True, "max_load": 5}
    assert entry.new_values == {"is_active": False, "max_load": 8}
    assert await session.get(Auditoria, entry.id) is not None


@pytest.mark.asyncio
async def test_historial_de_entidad_conserva_el_orden_de_los_cambios(service) -> None:
    audit_service, _session = service
    entity_id = uuid.uuid4()

    await audit_service.record_change(
        actor_id=None,
        action="user.created",
        entity_type="user",
        entity_id=entity_id,
        new_values={"is_active": True},
        created_at=datetime(2026, 10, 4, 19, 0, tzinfo=UTC),
    )
    await audit_service.record_change(
        actor_id=None,
        action="user.deactivated",
        entity_type="user",
        entity_id=entity_id,
        old_values={"is_active": True},
        new_values={"is_active": False},
        created_at=datetime(2026, 10, 4, 20, 0, tzinfo=UTC),
    )

    history = await audit_service.historial_entidad(entity_type="user", entity_id=entity_id)

    assert [item.action for item in history] == ["user.created", "user.deactivated"]
    assert history[1].old_values == {"is_active": True}
