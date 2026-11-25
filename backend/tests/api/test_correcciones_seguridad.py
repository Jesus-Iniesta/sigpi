"""Pruebas de las correcciones de seguridad de S5-08.

- `GET /usuarios` exige sesión (401) y permiso (403).
- La IP auditada solo sale de `X-Forwarded-For` si la conexión directa viene de un
  proxy de confianza (`TRUSTED_PROXIES`).

Ejercitan por HTTP el router, el servicio y el repositorio reales contra SQLite en
memoria; el usuario en sesión se reemplaza con `dependency_overrides`.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.permissions import RoleName
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.auditoria import Auditoria
from app.models.enums import UserType
from app.models.identity import Role, User

KNOWN_ACCOUNT = "uaem2026001"
VALID_PASSWORD = "ClaveSegura#2026"
CLIENT_IP = "198.51.100.20"
PROXY_IP = "10.0.0.5"
FORWARDED_IP = "203.0.113.7"


def _en_sesion(user_id: uuid.UUID, role: str) -> SimpleNamespace:
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
    admin_id = uuid.uuid4()

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            session.add_all(
                [
                    Role(name=RoleName.REQUESTER.value, description="Solicitante"),
                    User(
                        id=admin_id,
                        institutional_id="admin-001",
                        full_name="Administración",
                        email="admin@uaemex.mx",
                        user_type=UserType.ADMINISTRATIVE,
                        is_active=True,
                    ),
                ]
            )
            await session.commit()

    asyncio.run(prepare())

    async def override_session():
        async with maker() as session:
            yield session

    def como(role: str) -> None:
        fastapi_app.dependency_overrides[get_current_user] = lambda: _en_sesion(admin_id, role)

    async def ips_auditadas() -> list[str | None]:
        async with maker() as session:
            return list(await session.scalars(select(Auditoria.ip_address)))

    fastapi_app.dependency_overrides[get_session] = override_session
    try:
        yield SimpleNamespace(
            como=como,
            ips=lambda: asyncio.run(ips_auditadas()),
        )
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _cliente(ip: str) -> TestClient:
    return TestClient(fastapi_app, client=(ip, 50000))


# --- GET /usuarios exige sesión y permiso ---------------------------------------
def test_listar_usuarios_sin_sesion_responde_401(entorno) -> None:
    response = _cliente(CLIENT_IP).get("/usuarios")

    assert response.status_code == 401


def test_listar_usuarios_con_rol_sin_permiso_responde_403(entorno) -> None:
    entorno.como(RoleName.REQUESTER.value)

    response = _cliente(CLIENT_IP).get("/usuarios")

    assert response.status_code == 403


@pytest.mark.parametrize(
    "role",
    [
        RoleName.ADMINISTRATOR.value,
        RoleName.AUDITOR.value,  # lectura de cuentas (identity.read)
        RoleName.SUPPORT_AGENT.value,  # registro asistido: busca al solicitante
    ],
)
def test_listar_usuarios_con_permiso_responde_200(entorno, role) -> None:
    entorno.como(role)

    response = _cliente(CLIENT_IP).get("/usuarios")

    assert response.status_code == 200
    assert [u["institutional_id"] for u in response.json()] == ["admin-001"]


# --- IP auditada y proxies de confianza -----------------------------------------
def _alta(client: TestClient) -> None:
    response = client.post(
        "/usuarios",
        json={"institutional_id": KNOWN_ACCOUNT, "password": VALID_PASSWORD, "role": "requester"},
        headers={"X-Forwarded-For": f"{FORWARDED_IP}, {PROXY_IP}"},
    )
    assert response.status_code == 201, response.text


def test_sin_proxy_de_confianza_se_audita_la_ip_del_cliente_directo(entorno, monkeypatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxies", "")
    entorno.como(RoleName.ADMINISTRATOR.value)

    _alta(_cliente(CLIENT_IP))

    assert entorno.ips() == [CLIENT_IP]


def test_con_proxy_de_confianza_se_audita_la_ip_del_encabezado(entorno, monkeypatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxies", f"192.0.2.1, {PROXY_IP}")
    entorno.como(RoleName.ADMINISTRATOR.value)

    _alta(_cliente(PROXY_IP))

    assert entorno.ips() == [FORWARDED_IP]


def test_conexion_que_no_viene_del_proxy_configurado_ignora_el_encabezado(
    entorno, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "trusted_proxies", "10.0.0.0/24")
    entorno.como(RoleName.ADMINISTRATOR.value)

    _alta(_cliente(CLIENT_IP))

    assert entorno.ips() == [CLIENT_IP]
