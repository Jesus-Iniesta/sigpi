"""Pruebas del solicitante no localizado: estado «por verificar» (S3-10, HU-01.3)."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.dependencies import get_current_user
from app.db.base import Base
from app.db.session import get_session
from app.integrations.directory_client import StubDirectoryClient
from app.main import app as fastapi_app
from app.models.enums import RequestChannel, RequestStatus, UserType
from app.models.identity import User
from app.models.request import RequestLog
from app.repositories.solicitud_repository import SolicitudRepository
from app.schemas.request import RequestAssistedCreate, RequestCreate
from app.services.solicitud_service import SolicitudService

ACTIVE_ID = "uaem-local-001"
INACTIVE_ID = "uaem-baja-002"
UNKNOWN_ID = "desconocido-999"
# Perfil de ejemplo del directorio simulado que no tiene cuenta en SIGPI.
DIRECTORY_ONLY_ID = "uaem2026001"


def _user(user_id: uuid.UUID, institutional_id: str, active: bool) -> User:
    return User(
        id=user_id,
        institutional_id=institutional_id,
        full_name=f"Usuario {institutional_id}",
        email=f"{institutional_id}@example.test",
        user_type=UserType.ACADEMIC,
        is_active=active,
    )


@pytest.fixture
def db():
    """Base SQLite en memoria con un técnico, un solicitante activo y uno dado de baja."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"technician": uuid.uuid4(), "active": uuid.uuid4()}

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            session.add_all(
                [
                    _user(ids["technician"], "tec-001", True),
                    _user(ids["active"], ACTIVE_ID, True),
                    _user(uuid.uuid4(), INACTIVE_ID, False),
                ]
            )
            await session.commit()

    asyncio.run(prepare())
    try:
        yield maker, ids
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
def client(db):
    maker, ids = db

    async def override_session():
        async with maker() as session:
            yield session

    async def override_user() -> User:
        async with maker() as session:
            return await session.get(User, ids["technician"])

    fastapi_app.dependency_overrides[get_session] = override_session
    fastapi_app.dependency_overrides[get_current_user] = override_user
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()


def _body(**overrides):
    body = {
        "title": "Sin acceso al correo",
        "description": "No puede entrar a su buzón.",
        "physical_location": "Edificio B",
    }
    body.update(overrides)
    return body


def _register_assisted(maker, technician_id: uuid.UUID, institutional_id: str):
    """Registra una solicitud asistida con el servicio y devuelve (solicitud, bitácora)."""

    async def run():
        async with maker() as session:
            service = SolicitudService(
                SolicitudRepository(session), session, directory=StubDirectoryClient()
            )
            payload = RequestAssistedCreate(
                requester_institutional_id=institutional_id,
                title="Sin acceso al correo",
                description="No puede entrar a su buzón.",
                physical_location="Edificio B",
                channel=RequestChannel.PHONE,
            )
            request = await service.create_assisted_request(payload, registered_by_id=technician_id)
            result = await session.execute(
                select(RequestLog).where(RequestLog.request_id == request.id)
            )
            return request, list(result.scalars())

    return asyncio.run(run())


# --- Por HTTP: POST /solicitudes con identificador institucional ---------------


def test_solicitante_localizado_se_registra_normalmente(client, db) -> None:
    _maker, ids = db

    response = client.post("/solicitudes", json=_body(requester_institutional_id=ACTIVE_ID))

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "registered"
    assert data["requester_id"] == str(ids["active"])
    assert data["requester_institutional_id"] == ACTIVE_ID


def test_solicitante_no_localizado_queda_por_verificar(client) -> None:
    response = client.post("/solicitudes", json=_body(requester_institutional_id=UNKNOWN_ID))

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "pending_verification"
    assert data["requester_id"] is None
    assert data["requester_institutional_id"] == UNKNOWN_ID
    assert data["folio"] == "SIG-0001"


def test_solicitante_dado_de_baja_se_rechaza(client) -> None:
    response = client.post("/solicitudes", json=_body(requester_institutional_id=INACTIVE_ID))

    assert response.status_code == 422


def test_alta_exige_una_sola_referencia_al_solicitante(client, db) -> None:
    _maker, ids = db

    sin_referencia = client.post("/solicitudes", json=_body())
    con_ambas = client.post(
        "/solicitudes",
        json=_body(requester_id=str(ids["active"]), requester_institutional_id=ACTIVE_ID),
    )

    assert sin_referencia.status_code == 422
    assert con_ambas.status_code == 422


# --- A nivel de servicio: registro asistido y bitácora -------------------------


def test_asistido_localizado_deja_la_bitacora_como_registrada(db) -> None:
    maker, ids = db

    request, logs = _register_assisted(maker, ids["technician"], ACTIVE_ID)

    assert request.status == RequestStatus.REGISTERED
    assert request.requester_id == ids["active"]
    assert len(logs) == 1
    assert logs[0].author_id == ids["technician"]
    assert logs[0].new_status == RequestStatus.REGISTERED
    assert "por verificar" not in logs[0].notes


def test_asistido_no_localizado_queda_por_verificar_y_lo_explica(db) -> None:
    maker, ids = db

    request, logs = _register_assisted(maker, ids["technician"], UNKNOWN_ID)

    assert request.status == RequestStatus.PENDING_VERIFICATION
    assert request.requester_id is None
    assert request.requester_institutional_id == UNKNOWN_ID
    assert logs[0].new_status == RequestStatus.PENDING_VERIFICATION
    assert "no aparece en el directorio" in logs[0].notes


def test_asistido_reconocido_en_directorio_sin_cuenta_queda_por_verificar(db) -> None:
    maker, ids = db

    request, logs = _register_assisted(maker, ids["technician"], DIRECTORY_ONLY_ID)

    assert request.status == RequestStatus.PENDING_VERIFICATION
    assert request.requester_id is None
    assert "el directorio lo reconoce" in logs[0].notes


# --- Esquema ---------------------------------------------------------------------


def test_esquema_rechaza_ambas_referencias_y_ninguna() -> None:
    datos = {"title": "Solicitud", "description": "Descripcion", "physical_location": "Edificio A"}

    with pytest.raises(ValidationError):
        RequestCreate(requester_id=uuid.uuid4(), requester_institutional_id=ACTIVE_ID, **datos)
    with pytest.raises(ValidationError):
        RequestCreate(**datos)
