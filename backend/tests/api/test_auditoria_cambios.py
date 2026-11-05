"""Pruebas de la auditoría conectada a las acciones de administración (S2-08, HU-10.3).

Ejercitan por HTTP los routers, servicios y repositorios reales contra SQLite en
memoria. El usuario en sesión se reemplaza con `dependency_overrides`, igual que en
las pruebas de registro asistido; lo único que consulta `require_permission` son
sus roles.
"""

import asyncio
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.core.permissions import RoleName
from app.db.base import Base
from app.db.session import get_session
from app.integrations.directory_client import StubDirectoryClient
from app.main import app as fastapi_app
from app.models.auditoria import Auditoria
from app.models.catalog import AreaServicio, Categoria, Especialidad, Turno
from app.models.enums import UserType
from app.models.identity import Role, User, UserRole
from app.models.organization import OrganizationalUnit
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.catalog_repository import (
    CategoryRepository,
    ServiceAreaRepository,
    ShiftRepository,
    SpecialtyRepository,
    TechnicianRepository,
)
from app.repositories.sla_repository import SlaRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.catalog import ServiceAreaCreate
from app.schemas.sla import SlaAgreementCreate
from app.services.auditoria_service import AuditoriaService
from app.services.catalog_service import CatalogService
from app.services.sla_service import SlaService
from app.services.usuario_service import UsuarioService

KNOWN_ACCOUNT = "uaem2026001"
VALID_PASSWORD = "ClaveSegura#2026"
ADMIN_IP = "203.0.113.7"


def _en_sesion(user_id: uuid.UUID, role: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name=role))],
    )


class Entorno:
    """Cliente HTTP y acceso directo a la base para verificar lo que quedó guardado."""

    def __init__(self, client: TestClient, maker, ids: dict[str, uuid.UUID]) -> None:
        self.client = client
        self.maker = maker
        self.ids = ids

    def como(self, role: str, user_id: uuid.UUID | None = None) -> None:
        actor_id = user_id or self.ids["admin"]
        fastapi_app.dependency_overrides[get_current_user] = lambda: _en_sesion(actor_id, role)

    def sin_sesion(self) -> None:
        fastapi_app.dependency_overrides.pop(get_current_user, None)

    def registros(self, **filtros) -> list[Auditoria]:
        async def consultar() -> list[Auditoria]:
            async with self.maker() as session:
                query = select(Auditoria).order_by(Auditoria.created_at, Auditoria.id)
                for campo, valor in filtros.items():
                    query = query.where(getattr(Auditoria, campo) == valor)
                return list(await session.scalars(query))

        return asyncio.run(consultar())


@pytest.fixture
def entorno():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"admin": uuid.uuid4(), "unit": uuid.uuid4(), "technician": uuid.uuid4()}

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            session.add_all(
                [
                    Role(name=RoleName.REQUESTER.value, description="Solicitante"),
                    User(
                        id=ids["admin"],
                        institutional_id="admin-001",
                        full_name="Administración",
                        email="admin@uaemex.mx",
                        user_type=UserType.ADMINISTRATIVE,
                        is_active=True,
                    ),
                    OrganizationalUnit(
                        id=ids["unit"], name="DTIC", unit_type="department", code="DTIC"
                    ),
                    User(
                        id=ids["technician"],
                        institutional_id="tec-001",
                        full_name="Técnico",
                        email="tec@uaemex.mx",
                        user_type=UserType.TECHNICAL,
                        support_level="level_1",
                        max_load=5,
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
    env = Entorno(TestClient(fastapi_app), maker, ids)
    env.como(RoleName.ADMINISTRATOR.value)
    try:
        yield env
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _alta_usuario(env: Entorno) -> dict:
    response = env.client.post(
        "/usuarios",
        json={"institutional_id": KNOWN_ACCOUNT, "password": VALID_PASSWORD, "role": "requester"},
        headers={"X-Forwarded-For": f"{ADMIN_IP}, 10.0.0.1"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _catalogo(env: Entorno) -> dict[str, str]:
    area = env.client.post(
        "/catalog/areas",
        json={"unit_id": str(env.ids["unit"]), "name": "Infraestructura y redes"},
    )
    assert area.status_code == 201, area.text
    category = env.client.post(
        "/catalog/categories", json={"area_id": area.json()["id"], "name": "Redes"}
    )
    assert category.status_code == 201, category.text
    specialty = env.client.post(
        "/catalog/specialties",
        json={"category_id": category.json()["id"], "name": "Red cableada"},
    )
    assert specialty.status_code == 201, specialty.text
    shift = env.client.post("/catalog/shifts", json={"name": "Matutino"})
    assert shift.status_code == 201, shift.text
    return {
        "area": area.json()["id"],
        "category": category.json()["id"],
        "specialty": specialty.json()["id"],
        "shift": shift.json()["id"],
    }


# --- usuarios -------------------------------------------------------------------
def test_alta_de_usuario_deja_un_registro_con_autor_fecha_valores_e_ip(entorno) -> None:
    user = _alta_usuario(entorno)

    registros = entorno.registros(entity_type="user", entity_id=user["id"])

    assert len(registros) == 1
    registro = registros[0]
    assert registro.action == "usuario.creado"
    assert registro.actor_id == entorno.ids["admin"]
    assert registro.created_at is not None
    assert registro.ip_address == ADMIN_IP
    assert registro.old_values is None
    assert registro.new_values["institutional_id"] == KNOWN_ACCOUNT
    assert registro.new_values["email"] == "amartinez@uaemex.mx"
    assert registro.new_values["is_active"] is True
    assert registro.new_values["roles"] == ["requester"]


def test_modificacion_de_usuario_registra_solo_los_campos_que_cambiaron(entorno) -> None:
    user = _alta_usuario(entorno)

    response = entorno.client.patch(f"/usuarios/{user['id']}", json={"max_load": 7})
    assert response.status_code == 200, response.text

    registros = entorno.registros(action="usuario.modificado", entity_id=user["id"])
    assert len(registros) == 1
    registro = registros[0]
    assert registro.actor_id == entorno.ids["admin"]
    assert registro.created_at is not None
    assert registro.ip_address == "testclient"  # sin X-Forwarded-For se usa la IP del socket
    assert registro.old_values == {"max_load": None}
    assert registro.new_values == {"max_load": 7}


def test_desactivacion_de_usuario_deja_un_registro_con_valores_anterior_y_nuevo(
    entorno,
) -> None:
    user = _alta_usuario(entorno)

    response = entorno.client.delete(f"/usuarios/{user['id']}")
    assert response.status_code == 200, response.text

    registros = entorno.registros(action="usuario.desactivado", entity_id=user["id"])
    assert len(registros) == 1
    registro = registros[0]
    assert registro.entity_type == "user"
    assert registro.actor_id == entorno.ids["admin"]
    assert registro.created_at is not None
    assert registro.ip_address == "testclient"
    assert registro.old_values == {"is_active": True}
    assert registro.new_values == {"is_active": False}


# --- catálogo -------------------------------------------------------------------
def test_altas_del_catalogo_registran_un_evento_por_entidad(entorno) -> None:
    ids = _catalogo(entorno)

    esperados = {
        ("catalogo.area.creado", "service_area", ids["area"]),
        ("catalogo.categoria.creado", "category", ids["category"]),
        ("catalogo.especialidad.creado", "specialty", ids["specialty"]),
        ("catalogo.turno.creado", "shift", ids["shift"]),
    }
    registros = [r for r in entorno.registros() if r.action.startswith("catalogo.")]
    assert {(r.action, r.entity_type, r.entity_id) for r in registros} == esperados
    assert all(r.old_values is None and r.new_values for r in registros)
    assert all(r.actor_id == entorno.ids["admin"] for r in registros)


def test_edicion_de_tecnico_registra_solo_los_campos_modificados(entorno) -> None:
    ids = _catalogo(entorno)
    technician_id = str(entorno.ids["technician"])

    response = entorno.client.patch(
        f"/catalog/technicians/{technician_id}",
        json={"max_load": 9, "support_level": "level_1", "specialty_ids": [ids["specialty"]]},
    )
    assert response.status_code == 200, response.text

    registros = entorno.registros(action="catalogo.tecnico.modificado")
    assert len(registros) == 1
    registro = registros[0]
    assert registro.entity_type == "technician"
    assert registro.entity_id == technician_id
    # `support_level` se envió con el mismo valor: no cambió y no se registra.
    assert registro.old_values == {"max_load": 5, "specialty_ids": []}
    assert registro.new_values == {"max_load": 9, "specialty_ids": [ids["specialty"]]}


# --- acuerdos de servicio -------------------------------------------------------
def test_alta_de_acuerdo_y_de_version_quedan_auditadas(entorno) -> None:
    agreement = entorno.client.post("/sla/agreements", json={"is_default": True})
    assert agreement.status_code == 201, agreement.text
    agreement_id = agreement.json()["id"]
    versions = entorno.client.post(
        f"/sla/agreements/{agreement_id}/versions",
        json={
            "valid_from": "2026-01-01T00:00:00Z",
            "times": [
                {"priority": "P1", "first_response_minutes": 30, "resolution_minutes": 240},
                {"priority": "P4", "first_response_minutes": 120, "resolution_minutes": 960},
            ],
        },
    )
    assert versions.status_code == 201, versions.text

    acuerdo = entorno.registros(action="sla.acuerdo.creado")
    assert [(r.entity_type, r.entity_id) for r in acuerdo] == [("sla_agreement", agreement_id)]
    assert acuerdo[0].new_values["is_default"] is True
    versiones = entorno.registros(action="sla.version.creada")
    assert {r.entity_id for r in versiones} == {v["id"] for v in versions.json()}
    assert all(r.entity_type == "sla_version" and r.old_values is None for r in versiones)


# --- datos sensibles --------------------------------------------------------------
def _claves(valor) -> set[str]:
    if isinstance(valor, dict):
        return set(valor) | {k for v in valor.values() for k in _claves(v)}
    if isinstance(valor, list):
        return {k for v in valor for k in _claves(v)}
    return set()


def test_ningun_registro_contiene_password_ni_password_hash(entorno) -> None:
    user = _alta_usuario(entorno)
    entorno.client.patch(f"/usuarios/{user['id']}", json={"max_load": 3})
    entorno.client.delete(f"/usuarios/{user['id']}")
    ids = _catalogo(entorno)
    entorno.client.patch(
        f"/catalog/technicians/{entorno.ids['technician']}",
        json={"shift_id": ids["shift"]},
    )
    entorno.client.post("/sla/agreements", json={"is_default": True})

    registros = entorno.registros()

    assert len(registros) >= 8
    for registro in registros:
        for valores in (registro.old_values, registro.new_values):
            claves = _claves(valores)
            assert "password" not in claves
            assert "password_hash" not in claves
            assert VALID_PASSWORD not in str(valores)


# --- sesión y permisos en las acciones de administración --------------------------
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/usuarios"),
        ("patch", f"/usuarios/{uuid.uuid4()}"),
        ("delete", f"/usuarios/{uuid.uuid4()}"),
        ("post", "/catalog/areas"),
        ("patch", f"/catalog/technicians/{uuid.uuid4()}"),
        ("post", "/sla/agreements"),
        ("post", f"/sla/agreements/{uuid.uuid4()}/versions"),
    ],
)
def test_acciones_de_administracion_exigen_sesion_y_permiso(entorno, method, path) -> None:
    def llamar():
        return entorno.client.request(method.upper(), path, json={})

    entorno.sin_sesion()
    assert llamar().status_code == 401

    entorno.como(RoleName.REQUESTER.value, uuid.uuid4())
    assert llamar().status_code == 403
    assert entorno.registros() == []


# --- consulta de solo lectura ---------------------------------------------------
def test_get_auditoria_responde_403_a_un_solicitante(entorno) -> None:
    _alta_usuario(entorno)
    entorno.como(RoleName.REQUESTER.value, uuid.uuid4())

    response = entorno.client.get("/auditoria")

    assert response.status_code == 403


def test_get_auditoria_sin_sesion_responde_401(entorno) -> None:
    entorno.sin_sesion()

    assert entorno.client.get("/auditoria").status_code == 401


def test_get_auditoria_responde_200_a_un_auditor_en_orden_cronologico(entorno) -> None:
    user = _alta_usuario(entorno)
    entorno.client.patch(f"/usuarios/{user['id']}", json={"max_load": 4})
    entorno.client.delete(f"/usuarios/{user['id']}")
    _catalogo(entorno)
    entorno.como(RoleName.AUDITOR.value, uuid.uuid4())

    response = entorno.client.get(
        "/auditoria", params={"entity_type": "user", "entity_id": user["id"]}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [r["action"] for r in body] == [
        "usuario.creado",
        "usuario.modificado",
        "usuario.desactivado",
    ]
    fechas = [datetime.fromisoformat(r["created_at"]) for r in body]
    assert fechas == sorted(fechas)
    assert body[0]["actor_id"] == str(entorno.ids["admin"])
    assert body[0]["ip_address"] == ADMIN_IP


def test_get_auditoria_sin_filtros_devuelve_todo_en_orden_cronologico(entorno) -> None:
    _alta_usuario(entorno)
    _catalogo(entorno)
    entorno.como(RoleName.AUDITOR.value, uuid.uuid4())

    body = entorno.client.get("/auditoria").json()

    assert body[0]["action"] == "usuario.creado"
    assert [r["action"] for r in body[1:]] == [
        "catalogo.area.creado",
        "catalogo.categoria.creado",
        "catalogo.especialidad.creado",
        "catalogo.turno.creado",
    ]


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_la_bitacora_no_expone_endpoints_de_modificacion(entorno, method) -> None:
    response = entorno.client.request(method.upper(), "/auditoria")

    assert response.status_code == 405


# --- misma transacción ----------------------------------------------------------
class AuditoriaQueFalla(AuditoriaRepository):
    """Repositorio de auditoría que simula una falla al escribir el registro."""

    async def add(self, entry: Auditoria) -> Auditoria:
        raise RuntimeError("falla simulada al escribir la auditoría")


def _contar(maker, model) -> int:
    async def contar() -> int:
        async with maker() as session:
            return len(list(await session.scalars(select(model))))

    return asyncio.run(contar())


def _con_auditoria_que_falla(maker, caso):
    async def ejecutar() -> None:
        async with maker() as session:
            with pytest.raises(RuntimeError, match="falla simulada"):
                await caso(session, AuditoriaService(AuditoriaQueFalla(session)))

    asyncio.run(ejecutar())


def test_si_falla_la_auditoria_no_se_guarda_el_alta_de_usuario(entorno) -> None:
    usuarios_antes = _contar(entorno.maker, User)

    async def caso(session, auditoria):
        service = UsuarioService(UsuarioRepository(session), StubDirectoryClient(), auditoria)
        await service.create_user(
            institutional_id=KNOWN_ACCOUNT, password=VALID_PASSWORD, role=RoleName.REQUESTER
        )

    _con_auditoria_que_falla(entorno.maker, caso)

    assert _contar(entorno.maker, User) == usuarios_antes
    assert _contar(entorno.maker, Auditoria) == 0


def test_si_falla_la_auditoria_no_se_guarda_la_desactivacion(entorno) -> None:
    user = _alta_usuario(entorno)

    async def caso(session, auditoria):
        service = UsuarioService(UsuarioRepository(session), StubDirectoryClient(), auditoria)
        await service.deactivate_user(uuid.UUID(user["id"]))

    _con_auditoria_que_falla(entorno.maker, caso)

    async def sigue_activo() -> bool:
        async with entorno.maker() as session:
            return (await session.get(User, uuid.UUID(user["id"]))).is_active

    assert asyncio.run(sigue_activo()) is True


def test_si_falla_la_auditoria_no_se_guarda_el_alta_del_catalogo(entorno) -> None:
    async def caso(session, auditoria):
        service = CatalogService(
            areas=ServiceAreaRepository(session),
            categories=CategoryRepository(session),
            specialties=SpecialtyRepository(session),
            shifts=ShiftRepository(session),
            technicians=TechnicianRepository(session),
            auditoria=auditoria,
        )
        await service.create_area(
            ServiceAreaCreate(unit_id=entorno.ids["unit"], name="Soporte a usuarios")
        )

    _con_auditoria_que_falla(entorno.maker, caso)

    assert _contar(entorno.maker, AreaServicio) == 0


def test_si_falla_la_auditoria_no_se_guarda_el_acuerdo(entorno) -> None:
    async def caso(session, auditoria):
        service = SlaService(SlaRepository(session), auditoria)
        await service.create_agreement(SlaAgreementCreate(is_default=True))

    _con_auditoria_que_falla(entorno.maker, caso)

    assert _contar(entorno.maker, ServiceLevelAgreement) == 0


# --- cada escritura se confirma (los repositorios ya no hacen commit) -----------
def _en_sesion_nueva(maker, consulta):
    async def ejecutar():
        async with maker() as session:
            return await consulta(session)

    return asyncio.run(ejecutar())


def test_cada_escritura_de_administracion_queda_confirmada_en_una_sesion_nueva(
    entorno,
) -> None:
    """Lee desde una sesión independiente: solo ve lo que el servicio confirmó."""

    async def sembrar_rol(session):
        session.add(Role(name=RoleName.AUDITOR.value, description="Auditor"))
        await session.commit()

    _en_sesion_nueva(entorno.maker, sembrar_rol)

    # UsuarioRepository.add + assign_role
    user = _alta_usuario(entorno)
    user_id = uuid.UUID(user["id"])
    # UsuarioRepository.replace_roles + update_fields
    response = entorno.client.patch(f"/usuarios/{user_id}", json={"role": "auditor", "max_load": 6})
    assert response.status_code == 200, response.text
    assert response.json()["roles"] == ["auditor"]

    async def usuario(session):
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.roles).selectinload(UserRole.role))
        )
        return (await session.scalars(stmt)).one()

    guardado = _en_sesion_nueva(entorno.maker, usuario)
    assert [ur.role.name for ur in guardado.roles] == ["auditor"]
    assert guardado.max_load == 6

    # UsuarioRepository.deactivate
    assert entorno.client.delete(f"/usuarios/{user_id}").status_code == 200
    assert _en_sesion_nueva(entorno.maker, usuario).is_active is False

    # ServiceArea/Category/Specialty/ShiftRepository.create + TechnicianRepository.save
    ids = _catalogo(entorno)
    response = entorno.client.patch(
        f"/catalog/technicians/{entorno.ids['technician']}",
        json={"shift_id": ids["shift"], "specialty_ids": [ids["specialty"]]},
    )
    assert response.status_code == 200, response.text

    async def catalogo(session):
        tecnico = (
            await session.scalars(
                select(User)
                .where(User.id == entorno.ids["technician"])
                .options(selectinload(User.specialties))
            )
        ).one()
        return {
            "area": await session.get(AreaServicio, uuid.UUID(ids["area"])),
            "category": await session.get(Categoria, uuid.UUID(ids["category"])),
            "specialty": await session.get(Especialidad, uuid.UUID(ids["specialty"])),
            "shift": await session.get(Turno, uuid.UUID(ids["shift"])),
            "tecnico": (str(tecnico.shift_id), [str(s.id) for s in tecnico.specialties]),
        }

    guardado = _en_sesion_nueva(entorno.maker, catalogo)
    assert all(guardado[k] is not None for k in ("area", "category", "specialty", "shift"))
    assert guardado["tecnico"] == (ids["shift"], [ids["specialty"]])

    # SlaRepository.add_agreement + save_versions
    agreement = entorno.client.post("/sla/agreements", json={"is_default": True})
    assert agreement.status_code == 201, agreement.text
    agreement_id = uuid.UUID(agreement.json()["id"])
    versions = entorno.client.post(
        f"/sla/agreements/{agreement_id}/versions",
        json={
            "valid_from": "2026-01-01T00:00:00Z",
            "times": [{"priority": "P2", "first_response_minutes": 60, "resolution_minutes": 480}],
        },
    )
    assert versions.status_code == 201, versions.text

    async def sla(session):
        acuerdo = await session.get(ServiceLevelAgreement, agreement_id)
        filas = list(
            await session.scalars(
                select(ServiceLevelVersion).where(ServiceLevelVersion.agreement_id == agreement_id)
            )
        )
        return acuerdo, filas

    acuerdo, filas = _en_sesion_nueva(entorno.maker, sla)
    assert acuerdo is not None
    assert [(v.version, v.priority) for v in filas] == [(1, "P2")]
