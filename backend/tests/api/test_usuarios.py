"""Pruebas del alta de cuentas y de la cuenta no reconocida (S2-06, HU-10.1).

Ejercitan el router, el servicio y el repositorio reales de usuarios contra una
base de datos SQLite en memoria; solo el directorio institucional es el
cliente de prueba (`StubDirectoryClient`, que reconoce la cuenta
`uaem2026001`). Las consultas específicas de PostgreSQL se cubrirán con la base
de pruebas de S4-01.
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
from app.core.permissions import RoleName
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.identity import Role

KNOWN_ACCOUNT = "uaem2026001"
VALID_PASSWORD = "ClaveSegura#2026"


ADMIN_ID = uuid.uuid4()


def _administrador() -> SimpleNamespace:
    """Usuario en sesión con rol de administrador (lo que consulta `require_permission`)."""
    return SimpleNamespace(
        id=ADMIN_ID,
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name="administrator"))],
    )


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
    fastapi_app.dependency_overrides[get_current_user] = _administrador
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _alta(client: TestClient, institutional_id: str = KNOWN_ACCOUNT, role: str = "requester"):
    return client.post(
        "/usuarios",
        json={"institutional_id": institutional_id, "password": VALID_PASSWORD, "role": role},
    )


def test_alta_valida_crea_la_cuenta_con_los_datos_del_directorio(client) -> None:
    response = _alta(client)

    assert response.status_code == 201
    body = response.json()
    assert body["institutional_id"] == KNOWN_ACCOUNT
    assert body["full_name"] == "Ana Martínez Soto"
    assert body["email"] == "amartinez@uaemex.mx"
    assert body["is_active"] is True
    assert body["roles"] == ["requester"]
    assert "password" not in body
    assert "password_hash" not in body


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
        {
            "institutional_id": KNOWN_ACCOUNT,
            "password": VALID_PASSWORD,
            "role": "rol-que-no-existe",
        },
        {"institutional_id": "", "password": VALID_PASSWORD, "role": "requester"},
        {
            "institutional_id": KNOWN_ACCOUNT,
            "password": VALID_PASSWORD,
            "role": "requester",
            "max_load": -1,
        },
        {
            "institutional_id": KNOWN_ACCOUNT,
            "password": VALID_PASSWORD,
            "role": "requester",
            "campo_extra": "x",
        },
        {"password": VALID_PASSWORD, "role": "requester"},
        {"institutional_id": KNOWN_ACCOUNT, "role": "requester"},
        {"institutional_id": KNOWN_ACCOUNT, "password": "corta", "role": "requester"},
    ],
    ids=[
        "rol_invalido",
        "id_vacio",
        "carga_negativa",
        "campo_extra",
        "sin_id",
        "sin_contrasena",
        "contrasena_corta",
    ],
)
def test_datos_de_alta_invalidos_responden_422(client, payload) -> None:
    response = client.post("/usuarios", json=payload)

    assert response.status_code == 422


def test_cuenta_creada_puede_iniciar_sesion_con_su_correo(client) -> None:
    _alta(client)

    response = client.post(
        "/auth/login", json={"email": "amartinez@uaemex.mx", "password": VALID_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["user"]["institutional_id"] == KNOWN_ACCOUNT


STUDENT_ACCOUNT = "uaem2026005"
EXTERNAL_ACCOUNT = "ext2026001"
MENSAJE_CORREO = "El correo debe ser institucional (@uaemex.mx o @alumno.uaemex.mx)."


def test_alta_de_alumno_con_dominio_alumno_responde_201(client) -> None:
    response = _alta(client, institutional_id=STUDENT_ACCOUNT)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ldiazm@alumno.uaemex.mx"
    assert body["user_type"] == "student"


def test_alumno_creado_puede_iniciar_sesion_con_su_correo(client) -> None:
    _alta(client, institutional_id=STUDENT_ACCOUNT)

    response = client.post(
        "/auth/login", json={"email": "ldiazm@alumno.uaemex.mx", "password": VALID_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["user"]["institutional_id"] == STUDENT_ACCOUNT


def test_alta_con_correo_externo_responde_422_y_no_crea_el_usuario(client) -> None:
    response = _alta(client, institutional_id=EXTERNAL_ACCOUNT)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "non_institutional_email"
    assert "pexterno@gmail.com" in body["detail"]
    assert client.get("/usuarios").json() == []


@pytest.mark.parametrize(
    "email", ["alguien@gmail.com", "alguien@uaemex.mx.evil.com", "alguien@otro.uaemex.mx"]
)
def test_login_con_correo_no_institucional_responde_422_con_el_mensaje_nuevo(
    client, email: str
) -> None:
    response = client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})

    assert response.status_code == 422
    assert MENSAJE_CORREO in str(response.json()["detail"])
