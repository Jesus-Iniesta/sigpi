"""Pruebas del cuerpo de error de `/auth/login` (COR-07, S3-01 y HU-01.1).

El login debe responder con el mismo formato que el resto de la API
(`detail`, `code`, `request_id`) y conservar los intentos fallidos en `extra`.
Usa SQLite en memoria, igual que las demás pruebas de `tests/api`.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.identity import User

PASSWORD = "ClaveSegura#2026"
ACTIVE_EMAIL = "activa@uaemex.mx"
INACTIVE_EMAIL = "inactiva@uaemex.mx"


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
            for institutional_id, email, active in (
                ("uaem-activa", ACTIVE_EMAIL, True),
                ("uaem-inactiva", INACTIVE_EMAIL, False),
            ):
                session.add(
                    User(
                        institutional_id=institutional_id,
                        full_name="Cuenta de prueba",
                        email=email,
                        password_hash=hash_password(PASSWORD),
                        is_active=active,
                    )
                )
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


def _login(client: TestClient, email: str, password: str):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_credenciales_invalidas_usan_el_formato_uniforme(client) -> None:
    response = _login(client, ACTIVE_EMAIL, "incorrecta")

    assert response.status_code == 401
    body = response.json()
    assert set(body) == {"detail", "code", "request_id", "extra"}
    assert body["code"] == "invalid_credentials"
    assert body["detail"] == "Correo o contraseña incorrectos."
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["extra"] == {"failed_attempts": 1, "offer_password_recovery": False}


def test_correo_desconocido_no_revela_que_la_cuenta_no_existe(client) -> None:
    body = _login(client, "nadie@uaemex.mx", PASSWORD).json()

    assert body["code"] == "invalid_credentials"
    assert body["extra"] == {"failed_attempts": 0, "offer_password_recovery": False}


def test_al_llegar_al_maximo_de_intentos_se_ofrece_recuperar_la_contrasena(client) -> None:
    for _ in range(settings.max_failed_login_attempts - 1):
        _login(client, ACTIVE_EMAIL, "incorrecta")

    body = _login(client, ACTIVE_EMAIL, "incorrecta").json()

    assert body["extra"]["failed_attempts"] == settings.max_failed_login_attempts
    assert body["extra"]["offer_password_recovery"] is True


def test_cuenta_desactivada_responde_403_con_codigo_propio(client) -> None:
    response = _login(client, INACTIVE_EMAIL, PASSWORD)

    assert response.status_code == 403
    body = response.json()
    assert set(body) == {"detail", "code", "request_id"}
    assert body["code"] == "inactive_account"


def test_login_correcto_sigue_entregando_el_token(client) -> None:
    response = _login(client, ACTIVE_EMAIL, PASSWORD)

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "access_token" in response.cookies
