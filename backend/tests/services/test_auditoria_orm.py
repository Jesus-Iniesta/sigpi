"""Defensa de inalterabilidad de la auditoría en el ORM, sin PostgreSQL (COR-03, HU-10.3)."""

import inspect
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.exceptions import AuditLogImmutableError
from app.db.base import Base
from app.models.auditoria import Auditoria
from app.repositories.auditoria_repository import AuditoriaRepository


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with maker() as db_session:
        yield db_session
    await engine.dispose()


async def _persisted_entry(session: AsyncSession) -> Auditoria:
    entry_id = uuid.uuid4()
    entry = Auditoria(
        id=entry_id,
        action="audit.test.created",
        entity_type="audit_test",
        entity_id=str(entry_id),
        new_values={"value": "original"},
    )
    session.add(entry)
    await session.commit()
    return entry


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("column", "new_value"),
    [
        ("action", "audit.test.altered"),
        ("new_values", {"value": "alterado"}),
        ("actor_id", uuid.uuid4()),
    ],
)
async def test_modificar_y_flush_lanza_error(session, column, new_value) -> None:
    entry = await _persisted_entry(session)

    setattr(entry, column, new_value)

    with pytest.raises(AuditLogImmutableError):
        await session.flush()


@pytest.mark.asyncio
async def test_eliminar_y_flush_lanza_error(session) -> None:
    entry = await _persisted_entry(session)

    await session.delete(entry)

    with pytest.raises(AuditLogImmutableError):
        await session.flush()


@pytest.mark.asyncio
async def test_registro_rechazado_conserva_valores_tras_rollback(session) -> None:
    entry = await _persisted_entry(session)
    entry.action = "audit.test.altered"
    with pytest.raises(AuditLogImmutableError):
        await session.commit()

    await session.rollback()
    await session.refresh(entry)

    assert entry.action == "audit.test.created"


@pytest.mark.asyncio
async def test_asignar_el_mismo_valor_no_es_modificacion(session) -> None:
    entry = await _persisted_entry(session)

    entry.action = entry.action

    await session.flush()


@pytest.mark.asyncio
async def test_insertar_sigue_permitido(session) -> None:
    await _persisted_entry(session)
    entry = await _persisted_entry(session)

    assert await session.get(Auditoria, entry.id) is not None


def test_repositorio_no_expone_metodos_de_mutacion() -> None:
    forbidden_prefixes = ("update", "delete", "remove")
    public_methods = [
        name
        for name, _ in inspect.getmembers(AuditoriaRepository, callable)
        if not name.startswith("_")
    ]

    assert public_methods, "El repositorio debería exponer al menos un método público."
    assert not [name for name in public_methods if name.lower().startswith(forbidden_prefixes)]
