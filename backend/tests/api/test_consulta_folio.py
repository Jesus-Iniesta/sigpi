"""Pruebas de la consulta de una solicitud y del cierre por confirmación (S4-03, HU-04.3).

Cubren el criterio «cierre por confirmación»: una solicitud resuelta pasa a «Cerrada»
cuando se confirma la solución, queda constancia en la bitácora y cualquier otro
estado o identificador se rechaza sin modificar la solicitud.

La consulta por folio (`GET /solicitudes/{folio}`) la expone S4-01. Sus pruebas se
agregan en la sección final cuando ese endpoint esté integrado en `main`.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.enums import RequestChannel, RequestStatus, UserType
from app.models.identity import User
from app.models.request import Request


def _user(user_id: uuid.UUID, institutional_id: str) -> User:
    return User(
        id=user_id,
        institutional_id=institutional_id,
        full_name=f"Usuario {institutional_id}",
        email=f"{institutional_id}@example.test",
        user_type=UserType.ACADEMIC,
        is_active=True,
    )


def _como(user_id: uuid.UUID, role: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name=role))],
    )


@pytest.fixture
def entorno():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"tecnico": uuid.uuid4(), "solicitante": uuid.uuid4()}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            session.add_all(
                [_user(ids["tecnico"], "tec-001"), _user(ids["solicitante"], "sol-001")]
            )
            await session.commit()

    asyncio.run(preparar())
    try:
        yield maker, ids
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
def cliente(entorno):
    maker, ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como(
        ids["tecnico"], "support_agent"
    )
    try:
        yield TestClient(fastapi_app), maker, ids
    finally:
        fastapi_app.dependency_overrides.clear()


def _crear_solicitud(maker, ids, status: RequestStatus) -> uuid.UUID:
    async def crear() -> uuid.UUID:
        async with maker() as session:
            request = Request(
                requester_id=ids["solicitante"],
                folio="SIG-0001",
                title="No hay conexión a la red",
                description="El laboratorio perdió conectividad.",
                physical_location="Edificio A, laboratorio 2",
                channel=RequestChannel.PORTAL,
                status=status,
                urgency=2,
                impact=2,
            )
            session.add(request)
            await session.commit()
            return request.id

    return asyncio.run(crear())


# --- Cierre por confirmación ---------------------------------------------------------


def test_confirmar_una_solicitud_resuelta_la_cierra(cliente) -> None:
    client, maker, ids = cliente
    request_id = _crear_solicitud(maker, ids, RequestStatus.RESOLVED)

    respuesta = client.post(f"/solicitudes/{request_id}/confirmar", json={})

    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["status"] == "closed"
    assert datos["closed_at"] is not None


def test_confirmar_deja_constancia_en_la_bitacora(cliente) -> None:
    client, maker, ids = cliente
    request_id = _crear_solicitud(maker, ids, RequestStatus.RESOLVED)

    client.post(
        f"/solicitudes/{request_id}/confirmar",
        json={"notes": "El usuario confirma que ya funciona"},
    )
    entradas = client.get(f"/solicitudes/{request_id}/bitacora").json()

    ultima = entradas[-1]
    assert ultima["action"] == "Solicitud confirmada"
    assert ultima["previous_status"] == "resolved"
    assert ultima["new_status"] == "closed"
    assert ultima["author_id"] == str(ids["tecnico"])
    assert ultima["notes"] == "El usuario confirma que ya funciona"


@pytest.mark.parametrize(
    "estado",
    [
        RequestStatus.REGISTERED,
        RequestStatus.ASSIGNED,
        RequestStatus.IN_PROGRESS,
        RequestStatus.WAITING,
    ],
)
def test_confirmar_una_solicitud_no_resuelta_responde_409_y_no_la_modifica(cliente, estado) -> None:
    client, maker, ids = cliente
    request_id = _crear_solicitud(maker, ids, estado)

    respuesta = client.post(f"/solicitudes/{request_id}/confirmar", json={})

    assert respuesta.status_code == 409
    detalle = client.get(f"/solicitudes/{request_id}").json()
    assert detalle["status"] == estado.value
    assert detalle["closed_at"] is None


def test_confirmar_dos_veces_responde_409(cliente) -> None:
    client, maker, ids = cliente
    request_id = _crear_solicitud(maker, ids, RequestStatus.RESOLVED)

    primera = client.post(f"/solicitudes/{request_id}/confirmar", json={})
    segunda = client.post(f"/solicitudes/{request_id}/confirmar", json={})

    assert primera.status_code == 200
    assert segunda.status_code == 409
    entradas = client.get(f"/solicitudes/{request_id}/bitacora").json()
    assert [e["action"] for e in entradas].count("Solicitud confirmada") == 1


def test_confirmar_una_solicitud_inexistente_responde_404(cliente) -> None:
    client, _maker, _ids = cliente

    respuesta = client.post(f"/solicitudes/{uuid.uuid4()}/confirmar", json={})

    assert respuesta.status_code == 404


@pytest.mark.parametrize("rol", ["requester", "classifier", "auditor"])
def test_confirmar_exige_permiso_de_cierre(cliente, rol) -> None:
    client, maker, ids = cliente
    request_id = _crear_solicitud(maker, ids, RequestStatus.RESOLVED)
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como(ids["tecnico"], rol)

    respuesta = client.post(f"/solicitudes/{request_id}/confirmar", json={})

    assert respuesta.status_code == 403
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como(
        ids["tecnico"], "support_agent"
    )
    assert client.get(f"/solicitudes/{request_id}").json()["status"] == "resolved"


# --- Consulta por folio (pendiente de S4-01) -----------------------------------------
# TODO(S4-01): agregar aquí las pruebas de `GET /solicitudes/{folio}` cuando el endpoint
# esté en main: folio existente, folio inexistente (404) y acceso solo al solicitante.
