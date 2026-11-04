"""Pruebas de vigencia inmediata del catálogo técnico (S2-12, HU-11.1).

Usan SQLite en memoria con los routers, servicios y repositorios reales. Cada
prueba crea sus propios UUID y semillas para demostrar que una modificación del
catálogo queda disponible en la siguiente consulta sin reiniciar la aplicación.
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
from app.models.enums import UserType
from app.models.identity import User
from app.models.organization import OrganizationalUnit

ADMIN_ID = uuid.uuid4()


def _administrador() -> SimpleNamespace:
    """Usuario en sesión con rol de administrador (lo que consulta `require_permission`)."""
    return SimpleNamespace(
        id=ADMIN_ID,
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name="administrator"))],
    )


@pytest.fixture
def catalog_client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    unit_id = uuid.uuid4()
    technician_id = uuid.uuid4()

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            session.add_all(
                [
                    OrganizationalUnit(
                        id=unit_id,
                        name=f"Soporte {unit_id}",
                        unit_type="department",
                        code=f"SUP-{unit_id.hex[:8]}",
                    ),
                    User(
                        id=technician_id,
                        institutional_id=f"tec-{technician_id.hex[:8]}",
                        full_name="Técnico de vigencia",
                        email=f"tec-{technician_id.hex[:8]}@example.test",
                        user_type=UserType.TECHNICAL,
                        is_active=True,
                    ),
                ]
            )
            await session.commit()

    asyncio.run(prepare())

    async def override_session():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = override_session
    fastapi_app.dependency_overrides[get_current_user] = _administrador
    try:
        yield TestClient(fastapi_app), unit_id, technician_id
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _create_catalog(client: TestClient, unit_id: uuid.UUID) -> tuple[str, str, str, str]:
    area = client.post(
        "/catalog/areas",
        json={
            "unit_id": str(unit_id),
            "name": "Infraestructura y redes",
            "description": "Conectividad",
        },
    )
    assert area.status_code == 201, area.text
    area_id = area.json()["id"]

    category = client.post(
        "/catalog/categories",
        json={"area_id": area_id, "name": "Redes", "description": "Switches"},
    )
    assert category.status_code == 201, category.text
    category_id = category.json()["id"]

    specialty = client.post(
        "/catalog/specialties",
        json={"category_id": category_id, "name": "Red cableada"},
    )
    assert specialty.status_code == 201, specialty.text
    specialty_id = specialty.json()["id"]

    shift = client.post(
        "/catalog/shifts",
        json={"name": "Matutino"},
    )
    assert shift.status_code == 201, shift.text
    return area_id, category_id, specialty_id, shift.json()["id"]


def test_unidades_organizacionales_activas_se_listan_para_crear_areas(catalog_client) -> None:
    client, unit_id, _ = catalog_client

    response = client.get("/catalog/organizational-units")

    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "id": str(unit_id),
            "name": f"Soporte {unit_id}",
            "unit_type": "department",
            "code": f"SUP-{unit_id.hex[:8]}",
        }
    ]


def test_catalogo_creado_aparece_inmediatamente_en_listados(catalog_client) -> None:
    client, unit_id, _technician_id = catalog_client

    area_id, category_id, specialty_id, shift_id = _create_catalog(client, unit_id)

    assert any(item["id"] == area_id for item in client.get("/catalog/areas").json())
    assert any(item["id"] == category_id for item in client.get("/catalog/categories").json())
    assert any(item["id"] == specialty_id for item in client.get("/catalog/specialties").json())
    assert any(item["id"] == shift_id for item in client.get("/catalog/shifts").json())


def test_cambio_de_perfil_tecnico_es_visible_en_la_siguiente_consulta(catalog_client) -> None:
    client, unit_id, technician_id = catalog_client
    _area_id, _category_id, specialty_id, shift_id = _create_catalog(client, unit_id)

    update = client.patch(
        f"/catalog/technicians/{technician_id}",
        json={
            "support_level": "level_2",
            "shift_id": shift_id,
            "max_load": 8,
            "specialty_ids": [specialty_id],
        },
    )

    assert update.status_code == 200, update.text
    technician = client.get("/catalog/technicians").json()[0]
    assert technician["support_level"] == "level_2"
    assert technician["shift_id"] == shift_id
    assert technician["max_load"] == 8
    assert technician["specialty_ids"] == [specialty_id]


def test_filtro_por_especialidad_usa_la_configuracion_vigente(catalog_client) -> None:
    client, unit_id, technician_id = catalog_client
    _area_id, _category_id, specialty_id, _shift_id = _create_catalog(client, unit_id)

    before = client.get(f"/catalog/technicians?specialty_id={specialty_id}")
    assert before.status_code == 200
    assert before.json() == []

    response = client.patch(
        f"/catalog/technicians/{technician_id}",
        json={"specialty_ids": [specialty_id]},
    )
    assert response.status_code == 200, response.text

    after = client.get(f"/catalog/technicians?specialty_id={specialty_id}")
    assert after.status_code == 200
    assert [technician["id"] for technician in after.json()] == [str(technician_id)]


def test_actualizacion_rechaza_referencias_no_vigentes(catalog_client) -> None:
    client, _unit_id, technician_id = catalog_client
    missing_id = uuid.uuid4()

    missing_shift = client.patch(
        f"/catalog/technicians/{technician_id}",
        json={"shift_id": str(missing_id)},
    )
    missing_specialty = client.patch(
        f"/catalog/technicians/{technician_id}",
        json={"specialty_ids": [str(missing_id)]},
    )

    assert missing_shift.status_code == 422
    assert "does not exist" in missing_shift.json()["detail"]
    assert missing_specialty.status_code == 422
    assert "unknown specialties" in missing_specialty.json()["detail"]


# --- COR-04: opciones predefinidas ------------------------------------------------


def _create_category(client: TestClient, unit_id: uuid.UUID, name: str) -> str:
    area = client.post(
        "/catalog/areas", json={"unit_id": str(unit_id), "name": "Soporte a usuarios"}
    )
    assert area.status_code == 201, area.text
    category = client.post("/catalog/categories", json={"area_id": area.json()["id"], "name": name})
    assert category.status_code == 201, category.text
    return category.json()["id"]


def test_opciones_del_catalogo_se_publican(catalog_client) -> None:
    client, _unit_id, _ = catalog_client

    response = client.get("/catalog/options")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "Soporte a usuarios" in body["service_areas"]
    assert body["categories"] == ["Hardware", "Software", "Redes", "Cuentas y accesos"]
    hardware = next(group for group in body["specialties"] if group["category"] == "Hardware")
    assert "Equipo de cómputo" in hardware["names"]
    assert {"name": "Matutino", "start_minute": 420, "end_minute": 900} in body["shifts"]
    assert body["max_load"] == {"min": 1, "max": 15}


@pytest.mark.parametrize(
    "name",
    ["VLAN", "Equipo de cómputo"],  # fuera de la lista / de otra categoría (Hardware)
)
def test_especialidad_fuera_de_la_lista_de_su_categoria_responde_422(
    catalog_client, name: str
) -> None:
    client, unit_id, _ = catalog_client
    category_id = _create_category(client, unit_id, "Redes")

    response = client.post("/catalog/specialties", json={"category_id": category_id, "name": name})

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "catalog_option_not_allowed"
    assert "Red cableada" in body["detail"]


@pytest.mark.parametrize(
    ("path", "field", "value"),
    [
        ("/catalog/areas", "name", "Mesa de ayuda"),
        ("/catalog/categories", "name", "Impresoras"),
        ("/catalog/shifts", "name", "Nocturno"),
    ],
)
def test_nombres_fuera_de_la_lista_responden_422(
    catalog_client, path: str, field: str, value: str
) -> None:
    client, unit_id, _ = catalog_client
    payload: dict[str, str] = {field: value}
    if path == "/catalog/areas":
        payload["unit_id"] = str(unit_id)
    elif path == "/catalog/categories":
        payload["area_id"] = str(uuid.uuid4())

    response = client.post(path, json=payload)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "catalog_option_not_allowed"
    assert "Valores permitidos" in response.json()["detail"]


def test_turno_matutino_toma_el_horario_del_servidor(catalog_client) -> None:
    client, _unit_id, _ = catalog_client

    response = client.post("/catalog/shifts", json={"name": "Matutino"})

    assert response.status_code == 201, response.text
    assert response.json()["start_minute"] == 7 * 60
    assert response.json()["end_minute"] == 15 * 60


def test_turno_ya_no_acepta_horario_del_cliente(catalog_client) -> None:
    client, _unit_id, _ = catalog_client

    response = client.post(
        "/catalog/shifts", json={"name": "Matutino", "start_minute": 0, "end_minute": 60}
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "description",
    ["<script>alert(1)</script>", "texto con \x00 nulo", "salto\x1bescape", "x" * 301],
)
def test_descripcion_invalida_responde_422(catalog_client, description: str) -> None:
    client, unit_id, _ = catalog_client

    response = client.post(
        "/catalog/areas",
        json={"unit_id": str(unit_id), "name": "Soporte a usuarios", "description": description},
    )

    assert response.status_code == 422, response.text


def test_descripcion_se_recorta(catalog_client) -> None:
    client, unit_id, _ = catalog_client

    response = client.post(
        "/catalog/areas",
        json={
            "unit_id": str(unit_id),
            "name": "Soporte a usuarios",
            "description": "   Atención a usuarios   ",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["description"] == "Atención a usuarios"


@pytest.mark.parametrize("max_load", [0, 16])
def test_carga_maxima_fuera_de_rango_responde_422(catalog_client, max_load: int) -> None:
    client, _unit_id, technician_id = catalog_client

    response = client.patch(f"/catalog/technicians/{technician_id}", json={"max_load": max_load})

    assert response.status_code == 422, response.text


def test_carga_maxima_quince_es_valida(catalog_client) -> None:
    client, _unit_id, technician_id = catalog_client

    response = client.patch(f"/catalog/technicians/{technician_id}", json={"max_load": 15})

    assert response.status_code == 200, response.text
    assert response.json()["max_load"] == 15
