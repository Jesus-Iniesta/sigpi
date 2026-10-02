"""Pruebas del alta de cuentas y de la cuenta no reconocida (S2-06, HU-10.1).

Ejercitan el router, el servicio y el repositorio reales de usuarios contra una
base de datos SQLite en memoria; solo el directorio institucional es el
cliente de prueba (`StubDirectoryClient`, que reconoce la cuenta
`uaem2026001`). Las consultas específicas de PostgreSQL se cubrirán con la base
de pruebas de S4-01.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.core.permissions import RoleName
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.identity import Role

KNOWN_ACCOUNT = "uaem2026001"


@pytest.fixture
def client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            session.add(Role(name=RoleName.REQUESTER.value, description="Solicitante"))
            await session.commit()

    asyncio.run(prepare())

    async def override_session():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _alta(client: TestClient, institutional_id: str = KNOWN_ACCOUNT, role: str = "requester"):
    return client.post("/usuarios", json={"institutional_id": institutional_id, "role": role})


def test_alta_valida_crea_la_cuenta_con_los_datos_del_directorio(client) -> None:
    response = _alta(client)

    assert response.status_code == 201
    body = response.json()
    assert body["institutional_id"] == KNOWN_ACCOUNT
    assert body["full_name"] == "Ana Martínez Soto"
    assert body["email"] == "amartinez@uaemex.mx"
    assert body["is_active"] is True
    assert body["roles"] == ["requester"]


def test_alta_valida_aparece_en_el_listado_de_cuentas_activas(client) -> None:
    _alta(client)

    listado = client.get("/usuarios").json()

    assert [u["institutional_id"] for u in listado] == [KNOWN_ACCOUNT]


def test_cuenta_no_reconocida_por_el_directorio_responde_404(client) -> None:
    response = _alta(client, institutional_id="cuenta-inexistente")

    assert response.status_code == 404
    assert "cuenta-inexistente" in response.json()["detail"]


def test_cuenta_no_reconocida_no_crea_ningun_usuario(client) -> None:
    _alta(client, institutional_id="cuenta-inexistente")

    assert client.get("/usuarios").json() == []


def test_cuenta_ya_registrada_responde_409(client) -> None:
    _alta(client)

    response = _alta(client)

    assert response.status_code == 409
    assert KNOWN_ACCOUNT in response.json()["detail"]


def test_rol_no_configurado_responde_422(client) -> None:
    response = _alta(client, role=RoleName.AUDITOR.value)

    assert response.status_code == 422
    assert client.get("/usuarios").json() == []


@pytest.mark.parametrize(
    "payload",
    [
        {"institutional_id": KNOWN_ACCOUNT, "role": "rol-que-no-existe"},
        {"institutional_id": "", "role": "requester"},
        {"institutional_id": KNOWN_ACCOUNT, "role": "requester", "max_load": -1},
        {"institutional_id": KNOWN_ACCOUNT, "role": "requester", "campo_extra": "x"},
        {"role": "requester"},
    ],
    ids=["rol_invalido", "id_vacio", "carga_negativa", "campo_extra", "sin_id"],
)
def test_datos_de_alta_invalidos_responden_422(client, payload) -> None:
    response = client.post("/usuarios", json=payload)

    assert response.status_code == 422
