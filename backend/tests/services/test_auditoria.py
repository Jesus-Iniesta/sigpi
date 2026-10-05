"""Integration tests for the immutable audit-log trigger (S2-09, HU-10.3)."""

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import settings
from app.models.auditoria import Auditoria


@pytest_asyncio.fixture
async def audit_connection() -> AsyncGenerator[AsyncConnection]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            try:
                await connection.execute(text("SELECT 1 FROM audit_logs LIMIT 1"))
            except OperationalError as exc:
                pytest.skip(f"PostgreSQL no está disponible para la prueba: {exc}")
            await connection.rollback()
            yield connection
    finally:
        await engine.dispose()


async def _insert_audit_entry(connection: AsyncConnection) -> uuid.UUID:
    entry_id = uuid.uuid4()
    await connection.execute(
        insert(Auditoria).values(
            id=entry_id,
            actor_id=None,
            action="audit.test.created",
            entity_type="audit_test",
            entity_id=str(entry_id),
            old_values=None,
            new_values={"value": "original"},
            ip_address=None,
        )
    )
    return entry_id


@pytest.mark.asyncio
async def test_auditoria_rechaza_update_y_conserva_valores(audit_connection) -> None:
    async with audit_connection.begin():
        entry_id = await _insert_audit_entry(audit_connection)
        savepoint = await audit_connection.begin_nested()

        with pytest.raises(DBAPIError, match="append-only"):
            await audit_connection.execute(
                update(Auditoria)
                .where(Auditoria.id == entry_id)
                .values(new_values={"value": "altered"})
            )

        await savepoint.rollback()
        row = await audit_connection.execute(
            select(Auditoria.new_values).where(Auditoria.id == entry_id)
        )

        assert row.scalar_one() == {"value": "original"}


@pytest.mark.asyncio
async def test_auditoria_rechaza_delete_y_conserva_registro(audit_connection) -> None:
    async with audit_connection.begin():
        entry_id = await _insert_audit_entry(audit_connection)
        savepoint = await audit_connection.begin_nested()

        with pytest.raises(DBAPIError, match="append-only"):
            await audit_connection.execute(delete(Auditoria).where(Auditoria.id == entry_id))

        await savepoint.rollback()
        row = await audit_connection.execute(
            select(Auditoria.id).where(Auditoria.id == entry_id)
        )

        assert row.scalar_one() == entry_id
