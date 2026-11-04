"""Pruebas del modelo y de la API de acuerdos de servicio (S2-13, COR-05)."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.db.base import Base
from app.db.session import get_session
from app.domain.sla_options import AGREEMENT_DEFAULT_NAME, SERVICE_TYPE_NAMES
from app.main import app as fastapi_app
from app.models.catalog import AreaServicio, Categoria
from app.models.organization import OrganizationalUnit
from app.models.sla import ServiceLevelVersion


def test_sla_versions_are_unique_per_priority() -> None:
    constraints = ServiceLevelVersion.__table__.constraints

    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_sla_version_priority"
        and {column.name for column in constraint.columns}
        == {"agreement_id", "version", "priority"}
        for constraint in constraints
    )


def test_sla_versions_validate_priority_and_time_values() -> None:
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in ServiceLevelVersion.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_sla_priority_valid" in checks
    assert "ck_sla_first_response_positive" in checks
    assert "ck_sla_resolution_positive" in checks
    assert "ck_sla_valid_period" in checks


# --- COR-05: API de acuerdos con nombres predefinidos ------------------------
@pytest.fixture
def sla_client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    category_id = uuid.uuid4()

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            unit = OrganizationalUnit(name="DTIC", unit_type="department")
            session.add(unit)
            await session.flush()
            area = AreaServicio(unit_id=unit.id, name="Redes")
            session.add(area)
            await session.flush()
            session.add(Categoria(id=category_id, area_id=area.id, name="Conectividad"))
            await session.commit()

    asyncio.run(prepare())

    async def override_session():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(fastapi_app), str(category_id)
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_options_devuelve_los_tipos_de_servicio(sla_client) -> None:
    client, _ = sla_client

    response = client.get("/sla/options")

    assert response.status_code == 200
    assert response.json() == {
        "default_name": AGREEMENT_DEFAULT_NAME,
        "service_types": list(SERVICE_TYPE_NAMES),
    }


def test_post_con_nombre_libre_responde_422_sla_name_not_allowed(sla_client) -> None:
    client, category_id = sla_client

    response = client.post(
        "/sla/agreements", json={"name": "Nombre libre", "category_id": category_id}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "sla_name_not_allowed"


def test_post_predeterminado_ignora_el_nombre_enviado(sla_client) -> None:
    client, _ = sla_client

    response = client.post("/sla/agreements", json={"name": "Otro", "is_default": True})

    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Acuerdo general de servicio"


def test_post_duplicado_activo_con_mismo_nombre_y_categoria_responde_409(sla_client) -> None:
    client, category_id = sla_client
    body = {"name": SERVICE_TYPE_NAMES[2], "category_id": category_id}

    assert client.post("/sla/agreements", json=body).status_code == 201
    response = client.post("/sla/agreements", json=body)

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"
    assert SERVICE_TYPE_NAMES[2] in response.json()["detail"]
