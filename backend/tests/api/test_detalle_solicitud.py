"""Pruebas del detalle de la solicitud y su bitácora (soporte de S3-13, HU-04.1).

La pantalla `SolicitudDetallePage` consume dos endpoints:

- `GET /solicitudes/{id}`: datos de la solicitud, diagnóstico y solución.
- `GET /solicitudes/{id}/bitacora`: historial de acciones, de la más antigua a la más reciente.
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


def _crear_solicitud(maker, ids, status: RequestStatus = RequestStatus.ASSIGNED) -> uuid.UUID:
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


# --- GET /solicitudes/{id} -----------------------------------------------------------


def test_el_detalle_devuelve_los_datos_de_la_solicitud(cliente) -> None:
    client, maker, ids = cliente
    request_id = _crear_solicitud(maker, ids)

    respuesta = client.get(f"/solicitudes/{request_id}")

    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["id"] == str(request_id)
    assert datos["folio"] == "SIG-0001"
    assert datos["title"] == "No hay conexión a la red"
    assert datos["status"] == "assigned"
    assert datos["requester_id"] == str(ids["solicitante"])
    assert datos["diagnosis"] is None
    assert datos["solution"] is None


def test_el_detalle_refleja_el_diagnostico_y_la_solucion(cliente) -> None:
    client, maker, ids = cliente
    request_id = _crear_solicitud(maker, ids)

    client.post(f"/solicitudes/{request_id}/diagnostico", json={"diagnosis": "Cable dañado"})
    client.post(f"/solicitudes/{request_id}/resolver", json={"solution": "Se cambió el cable"})
    datos = client.get(f"/solicitudes/{request_id}").json()

    assert datos["status"] == "resolved"
    assert datos["diagnosis"] == "Cable dañado"
    assert datos["solution"] == "Se cambió el cable"
    assert datos["resolution_minutes"] is not None


def test_el_detalle_de_una_solicitud_inexistente_responde_404(cliente) -> None:
    client, _maker, _ids = cliente

    respuesta = client.get(f"/solicitudes/{uuid.uuid4()}")

    assert respuesta.status_code == 404


def test_el_detalle_rechaza_un_identificador_que_no_es_uuid(cliente) -> None:
    client, _maker, _ids = cliente

    respuesta = client.get("/solicitudes/SIG-0001")

    assert respuesta.status_code == 422


@pytest.mark.parametrize("rol", ["requester", "classifier", "auditor"])
def test_el_detalle_exige_permiso_de_atencion(cliente, rol) -> None:
    client, maker, ids = cliente
    request_id = _crear_solicitud(maker, ids)
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como(ids["tecnico"], rol)

    respuesta = client.get(f"/solicitudes/{request_id}")

    assert respuesta.status_code == 403


def test_el_detalle_exige_iniciar_sesion(entorno) -> None:
    maker, _ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    try:
        respuesta = TestClient(fastapi_app).get(f"/solicitudes/{uuid.uuid4()}")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert respuesta.status_code == 401


# --- GET /solicitudes/{id}/bitacora --------------------------------------------------


def test_la_bitacora_recorre_el_ciclo_de_vida_en_orden(cliente) -> None:
    client, maker, ids = cliente
    request_id = _crear_solicitud(maker, ids)

    client.post(f"/solicitudes/{request_id}/iniciar")
    client.post(f"/solicitudes/{request_id}/diagnostico", json={"diagnosis": "Cable dañado"})
    client.post(f"/solicitudes/{request_id}/resolver", json={"solution": "Se cambió el cable"})
    client.post(f"/solicitudes/{request_id}/confirmar", json={})
    respuesta = client.get(f"/solicitudes/{request_id}/bitacora")

    assert respuesta.status_code == 200, respuesta.text
    entradas = respuesta.json()
    assert [e["action"] for e in entradas] == [
        "Atención iniciada",
        "Diagnóstico registrado",
        "Solicitud resuelta",
        "Solicitud confirmada",
    ]
    assert [e["new_status"] for e in entradas] == [
        "in_progress",
        "in_progress",
        "resolved",
        "closed",
    ]
    assert all(e["author_id"] == str(ids["tecnico"]) for e in entradas)


def test_la_bitacora_de_una_solicitud_sin_acciones_esta_vacia(cliente) -> None:
    client, maker, ids = cliente
    request_id = _crear_solicitud(maker, ids)

    respuesta = client.get(f"/solicitudes/{request_id}/bitacora")

    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_la_bitacora_de_una_solicitud_inexistente_responde_404(cliente) -> None:
    client, _maker, _ids = cliente

    respuesta = client.get(f"/solicitudes/{uuid.uuid4()}/bitacora")

    assert respuesta.status_code == 404
