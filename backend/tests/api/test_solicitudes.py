"""Pruebas del alta de solicitudes y folio consecutivo (S2-16, HU-01.1)."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.enums import UserType
from app.models.identity import User


@pytest.fixture
def request_client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    requester_id = uuid.uuid4()
    category_id = uuid.uuid4()

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            session.add(
                User(
                    id=requester_id,
                    institutional_id=f"req-{requester_id.hex[:8]}",
                    full_name="Solicitante de prueba",
                    email=f"req-{requester_id.hex[:8]}@example.test",
                    user_type=UserType.ACADEMIC,
                    is_active=True,
                )
            )
            await session.commit()

    asyncio.run(prepare())

    async def override_session():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(fastapi_app), requester_id, category_id
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _payload(requester_id: uuid.UUID, **overrides):
    payload = {
        "requester_id": str(requester_id),
        "title": "No hay conexión a la red",
        "description": "El laboratorio perdió conectividad.",
        "physical_location": "Edificio A, laboratorio 2",
        "channel": "portal",
        "urgency": 2,
        "impact": 2,
    }
    payload.update(overrides)
    return payload


def test_alta_asigna_folio_y_estado_inicial(request_client) -> None:
    client, requester_id, _category_id = request_client

    response = client.post("/solicitudes", json=_payload(requester_id))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["folio"] == "SIG-0001"
    assert body["status"] == "registered"
    assert body["requester_id"] == str(requester_id)


def test_folio_es_consecutivo_y_persiste_entre_altas(request_client) -> None:
    client, requester_id, _category_id = request_client

    first = client.post("/solicitudes", json=_payload(requester_id, title="Primera solicitud"))
    second = client.post("/solicitudes", json=_payload(requester_id, title="Segunda solicitud"))

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["folio"] == "SIG-0001"
    assert second.json()["folio"] == "SIG-0002"


def test_rn02_rechaza_solicitante_inexistente_o_inactivo(request_client) -> None:
    client, _requester_id, _category_id = request_client

    response = client.post("/solicitudes", json=_payload(uuid.uuid4()))

    assert response.status_code == 422
    assert "requester" in response.json()["detail"]


def test_rn02_rechaza_solicitante_inactivo(request_client) -> None:
    client, _requester_id, _category_id = request_client
    client_id = uuid.uuid4()

    # La prueba crea un usuario inactivo a través del mismo esquema persistente.
    session_override = fastapi_app.dependency_overrides[get_session]

    async def add_inactive():
        async for session in session_override():
            session.add(
                User(
                    id=client_id,
                    institutional_id=f"inactive-{client_id.hex[:8]}",
                    full_name="Solicitante inactivo",
                    email=f"inactive-{client_id.hex[:8]}@example.test",
                    user_type=UserType.ACADEMIC,
                    is_active=False,
                )
            )
            await session.commit()

    asyncio.run(add_inactive())
    response = client.post("/solicitudes", json=_payload(requester_id=client_id))

    assert response.status_code == 422
    assert "inactive" in response.json()["detail"]


def test_rn03_rechaza_categoria_inexistente(request_client) -> None:
    client, requester_id, _category_id = request_client

    response = client.post(
        "/solicitudes",
        json=_payload(requester_id, category_id=str(uuid.uuid4())),
    )

    assert response.status_code == 422
    assert "category" in response.json()["detail"]


@pytest.mark.parametrize(
    "invalid_field",
    ["title", "description", "physical_location"],
)
def test_alta_rechaza_datos_obligatorios_invalidos(request_client, invalid_field) -> None:
    client, requester_id, _category_id = request_client
    payload = _payload(requester_id)
    payload[invalid_field] = ""

    response = client.post("/solicitudes", json=payload)

    assert response.status_code == 422
