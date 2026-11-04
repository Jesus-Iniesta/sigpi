"""Pruebas de integración de la inalterabilidad de audit_logs en PostgreSQL (S2-09, HU-10.3).

Requieren una base de datos PostgreSQL con las migraciones aplicadas. Si no está
disponible se saltan, salvo que exista la variable `SIGPI_REQUIRE_DB` (la define el CI):
en ese caso el fixture falla para que las pruebas nunca se omitan en silencio.

Cada prueba trabaja dentro de una transacción que se revierte al final, así que no deja
registros en la tabla (que, por diseño, no se pueden borrar).
"""

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import settings
from app.models.auditoria import Auditoria

ORIGINAL_VALUES: dict[str, Any] = {
    "action": "audit.test.created",
    "old_values": {"value": "anterior"},
    "new_values": {"value": "original"},
    "actor_id": None,
    "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
}


def _db_unavailable(reason: str) -> None:
    message = f"PostgreSQL no está disponible para la prueba: {reason}"
    if os.environ.get("SIGPI_REQUIRE_DB"):
        pytest.fail(f"{message} (SIGPI_REQUIRE_DB está definida)")
    pytest.skip(message)


@pytest_asyncio.fixture
async def audit_connection() -> AsyncGenerator[AsyncConnection]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        try:
            connection = await engine.connect()
        except (OSError, DBAPIError) as exc:
            _db_unavailable(str(exc))
        try:
            try:
                await connection.execute(text("SELECT 1 FROM audit_logs LIMIT 1"))
            except DBAPIError as exc:
                _db_unavailable(str(exc))
            # La transacción que abrió la consulta anterior queda activa durante la prueba
            # y se revierte al final.
            yield connection
        finally:
            await connection.rollback()
            await connection.close()
    finally:
        await engine.dispose()


async def _insert_audit_entry(connection: AsyncConnection) -> uuid.UUID:
    entry_id = uuid.uuid4()
    await connection.execute(
        insert(Auditoria).values(
            id=entry_id,
            entity_type="audit_test",
            entity_id=str(entry_id),
            ip_address=None,
            **ORIGINAL_VALUES,
        )
    )
    return entry_id


async def _count(connection: AsyncConnection) -> int:
    return (await connection.execute(select(func.count()).select_from(Auditoria))).scalar_one()


async def _assert_rejected(connection: AsyncConnection, statement: Any) -> None:
    savepoint = await connection.begin_nested()
    with pytest.raises(DBAPIError, match="append-only"):
        await connection.execute(statement)
    await savepoint.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("column", "new_value"),
    [
        ("action", "audit.test.altered"),
        ("old_values", {"value": "alterado"}),
        ("new_values", {"value": "alterado"}),
        ("actor_id", uuid.uuid4()),
        ("created_at", datetime(2030, 1, 1, tzinfo=UTC)),
    ],
)
async def test_auditoria_rechaza_update_de_cada_columna_y_conserva_valor(
    audit_connection, column, new_value
) -> None:
    entry_id = await _insert_audit_entry(audit_connection)

    await _assert_rejected(
        audit_connection,
        update(Auditoria).where(Auditoria.id == entry_id).values({column: new_value}),
    )

    row = await audit_connection.execute(
        select(getattr(Auditoria, column)).where(Auditoria.id == entry_id)
    )
    assert row.scalar_one() == ORIGINAL_VALUES[column]


@pytest.mark.asyncio
async def test_auditoria_rechaza_delete_individual_y_conserva_registro(audit_connection) -> None:
    entry_id = await _insert_audit_entry(audit_connection)

    await _assert_rejected(audit_connection, delete(Auditoria).where(Auditoria.id == entry_id))

    row = await audit_connection.execute(select(Auditoria.id).where(Auditoria.id == entry_id))
    assert row.scalar_one() == entry_id


@pytest.mark.asyncio
async def test_auditoria_rechaza_delete_sin_where(audit_connection) -> None:
    await _insert_audit_entry(audit_connection)
    before = await _count(audit_connection)

    await _assert_rejected(audit_connection, delete(Auditoria))

    assert await _count(audit_connection) == before


@pytest.mark.asyncio
async def test_auditoria_rechaza_truncate_y_conserva_filas(audit_connection) -> None:
    await _insert_audit_entry(audit_connection)
    before = await _count(audit_connection)

    await _assert_rejected(audit_connection, text("TRUNCATE audit_logs"))

    assert await _count(audit_connection) == before


@pytest.mark.asyncio
async def test_auditoria_permite_insertar(audit_connection) -> None:
    before = await _count(audit_connection)

    entry_id = await _insert_audit_entry(audit_connection)

    assert await _count(audit_connection) == before + 1
    row = await audit_connection.execute(
        select(Auditoria.new_values).where(Auditoria.id == entry_id)
    )
    assert row.scalar_one() == ORIGINAL_VALUES["new_values"]
