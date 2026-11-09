"""Pruebas de la consulta del solicitante por folio y de la confirmación (S4-01, HU-04.3).

- `GET /mis-solicitudes`: solicitudes propias, de la más reciente a la más antigua.
- `GET /mis-solicitudes/{folio}`: estatus, prioridad, fecha compromiso, técnico y bitácora
  resumida, sin las notas internas del técnico.
- `POST /mis-solicitudes/{folio}/confirmar`: cierra una solicitud «Resuelta» propia.
- El folio de otra persona responde 404, igual que uno inexistente.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.core.permissions import Permission, RoleName, has_permission
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.catalog import Categoria
from app.models.enums import Priority, RequestChannel, RequestStatus, UserType, WaitReason
from app.models.identity import User
from app.models.request import Request, RequestAssignment, RequestLog, RequestSlaPause
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.services import notificacion_service, sla_clock_service

INICIO = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
NOTA_INTERNA = "Nota interna: el switch del piso 2 tiene la contraseña por defecto."


def _como(user_id: uuid.UUID, role: str = "requester") -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name=role))],
    )


def _utc(texto: str) -> datetime:
    """Lee una fecha ISO de la API; SQLite la devuelve sin zona, así que se asume UTC."""
    valor = datetime.fromisoformat(texto)
    return valor if valor.tzinfo else valor.replace(tzinfo=UTC)


@pytest.fixture
def entorno():
    """Base SQLite con un solicitante, otra persona, un técnico y tres solicitudes.

    - SIG-0001 (del solicitante): asignada al técnico, SLA de 240 min, 60 min en espera
      y dos entradas en la bitácora con notas internas.
    - SIG-0002 (del solicitante): resuelta, lista para confirmarse.
    - SIG-0003 (de otra persona): resuelta.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {key: uuid.uuid4() for key in ("solicitante", "otra", "tecnico", "categoria")}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            for key, nombre in (
                ("solicitante", "Sara Solicitante"),
                ("otra", "Olga Otra"),
                ("tecnico", "Tomás Técnico"),
            ):
                session.add(
                    User(
                        id=ids[key],
                        institutional_id=f"u-{ids[key].hex[:8]}",
                        full_name=nombre,
                        email=f"{key}@example.test",
                        user_type=UserType.ACADEMIC,
                    )
                )
            session.add(Categoria(id=ids["categoria"], area_id=uuid.uuid4(), name="Redes"))
            acuerdo = ServiceLevelAgreement(name="Acuerdo general", is_default=True)
            session.add(acuerdo)
            await session.flush()
            version = ServiceLevelVersion(
                agreement_id=acuerdo.id,
                version=1,
                priority=Priority.P2,
                first_response_minutes=30,
                resolution_minutes=240,
                valid_from=INICIO - timedelta(days=30),
            )
            session.add(version)
            await session.flush()

            def solicitud(folio, requester, status, dias):
                return Request(
                    id=uuid.uuid4(),
                    requester_id=ids[requester],
                    category_id=ids["categoria"],
                    service_level_version_id=version.id,
                    folio=folio,
                    title=f"Solicitud {folio}",
                    description="No hay red.",
                    physical_location="Edificio B",
                    channel=RequestChannel.PORTAL,
                    status=status,
                    priority=Priority.P2,
                    created_at=INICIO + timedelta(days=dias),
                )

            asignada = solicitud("SIG-0001", "solicitante", RequestStatus.ASSIGNED, 0)
            resuelta = solicitud("SIG-0002", "solicitante", RequestStatus.RESOLVED, 1)
            ajena = solicitud("SIG-0003", "otra", RequestStatus.RESOLVED, 2)
            session.add_all([asignada, resuelta, ajena])
            await session.flush()
            session.add_all(
                [
                    RequestAssignment(
                        request_id=asignada.id,
                        technician_id=ids["tecnico"],
                        assigned_at=INICIO,
                    ),
                    RequestSlaPause(
                        request_id=asignada.id,
                        reason=WaitReason.EXTERNAL_INPUT,
                        started_by_id=ids["tecnico"],
                        started_at=INICIO + timedelta(minutes=30),
                        ended_at=INICIO + timedelta(minutes=90),
                    ),
                    RequestLog(
                        request_id=asignada.id,
                        author_id=ids["tecnico"],
                        previous_status=RequestStatus.ASSIGNED,
                        new_status=RequestStatus.IN_PROGRESS,
                        action="Atención iniciada",
                        notes=NOTA_INTERNA,
                        created_at=INICIO + timedelta(minutes=10),
                    ),
                    RequestLog(
                        request_id=asignada.id,
                        author_id=ids["tecnico"],
                        previous_status=RequestStatus.IN_PROGRESS,
                        new_status=RequestStatus.WAITING,
                        action="Reloj del SLA suspendido",
                        notes=NOTA_INTERNA,
                        created_at=INICIO + timedelta(minutes=30),
                    ),
                ]
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
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como(ids["solicitante"])
    try:
        yield TestClient(fastapi_app), maker, ids
    finally:
        fastapi_app.dependency_overrides.clear()


def _leer(maker, folio: str) -> Request:
    """Lee la solicitud con una sesión nueva: solo ve lo que quedó confirmado en la base."""

    async def leer() -> Request:
        async with maker() as session:
            return (await session.scalars(select(Request).where(Request.folio == folio))).one()

    return asyncio.run(leer())


# --- GET /mis-solicitudes ------------------------------------------------------------


def test_la_lista_trae_solo_las_solicitudes_propias_de_la_mas_reciente_a_la_mas_antigua(
    cliente,
) -> None:
    client, _maker, _ids = cliente

    respuesta = client.get("/mis-solicitudes")

    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert [d["folio"] for d in datos] == ["SIG-0002", "SIG-0001"]
    assert set(datos[0]) == {"folio", "title", "status", "priority", "created_at"}
    assert datos[0]["status"] == "resolved"
    assert datos[0]["priority"] == "P2"


# --- GET /mis-solicitudes/{folio} ----------------------------------------------------


def test_el_solicitante_consulta_su_folio_con_estatus_prioridad_fecha_compromiso_y_bitacora(
    cliente,
) -> None:
    client, _maker, _ids = cliente

    respuesta = client.get("/mis-solicitudes/SIG-0001")

    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["folio"] == "SIG-0001"
    assert datos["status"] == "assigned"
    assert datos["priority"] == "P2"
    assert datos["category"] == "Redes"
    assert datos["technician"] == "Tomás Técnico"
    # 09:00 + 240 min de SLA + 60 min en espera = 14:00.
    assert _utc(datos["due_at"]) == INICIO + timedelta(hours=5)
    assert [(e["action"], e["new_status"]) for e in datos["log"]] == [
        ("Atención iniciada", "in_progress"),
        ("Reloj del SLA suspendido", "waiting"),
    ]
    assert _utc(datos["log"][0]["created_at"]) == INICIO + timedelta(minutes=10)


def test_la_bitacora_resumida_no_expone_las_notas_internas(cliente) -> None:
    client, _maker, _ids = cliente

    respuesta = client.get("/mis-solicitudes/SIG-0001")

    assert respuesta.status_code == 200
    assert NOTA_INTERNA not in respuesta.text
    assert all(set(e) == {"action", "new_status", "created_at"} for e in respuesta.json()["log"])


def test_el_folio_se_acepta_sin_distinguir_mayusculas(cliente) -> None:
    client, _maker, _ids = cliente

    respuesta = client.get("/mis-solicitudes/sig-0001")

    assert respuesta.status_code == 200
    assert respuesta.json()["folio"] == "SIG-0001"


def test_sin_tecnico_ni_bitacora_el_detalle_los_deja_vacios(cliente) -> None:
    client, _maker, _ids = cliente

    datos = client.get("/mis-solicitudes/SIG-0002").json()

    assert datos["technician"] is None
    assert datos["log"] == []


@pytest.mark.parametrize("folio", ["SIG-0003", "SIG-9999"])
def test_el_folio_ajeno_o_inexistente_responde_404(cliente, folio) -> None:
    client, _maker, _ids = cliente

    respuesta = client.get(f"/mis-solicitudes/{folio}")

    assert respuesta.status_code == 404
    assert respuesta.json()["code"] == "not_found"


def test_el_404_del_folio_ajeno_es_identico_al_del_inexistente(cliente) -> None:
    client, _maker, _ids = cliente

    ajeno = client.get("/mis-solicitudes/SIG-0003").json()
    inexistente = client.get("/mis-solicitudes/SIG-9999").json()

    assert ajeno["detail"] == inexistente["detail"]


# --- POST /mis-solicitudes/{folio}/confirmar -----------------------------------------


def test_confirmar_una_solicitud_resuelta_propia_la_cierra_y_lo_guarda(cliente) -> None:
    client, maker, _ids = cliente

    respuesta = client.post("/mis-solicitudes/SIG-0002/confirmar", json={"notes": "Funciona"})

    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["status"] == "closed"
    assert datos["closed_at"] is not None
    assert datos["log"][-1] == {
        "action": "Solicitud confirmada",
        "new_status": "closed",
        "created_at": datos["log"][-1]["created_at"],
    }
    # Una sesión nueva ve el cambio: el servicio confirmó la transacción (commit).
    guardada = _leer(maker, "SIG-0002")
    assert guardada.status == RequestStatus.CLOSED
    assert guardada.closed_at is not None


def test_confirmar_acepta_el_cuerpo_vacio(cliente) -> None:
    client, _maker, _ids = cliente

    respuesta = client.post("/mis-solicitudes/sig-0002/confirmar")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["status"] == "closed"


def test_confirmar_una_solicitud_que_no_esta_resuelta_responde_422(cliente) -> None:
    client, maker, _ids = cliente

    respuesta = client.post("/mis-solicitudes/SIG-0001/confirmar", json={})

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["code"] == "business_rule_violation"
    assert "no puede confirmarse" in cuerpo["detail"]
    assert _leer(maker, "SIG-0001").status == RequestStatus.ASSIGNED


def test_confirmar_el_folio_de_otra_persona_responde_404_y_no_lo_cierra(cliente) -> None:
    client, maker, _ids = cliente

    respuesta = client.post("/mis-solicitudes/SIG-0003/confirmar", json={})

    assert respuesta.status_code == 404
    assert _leer(maker, "SIG-0003").status == RequestStatus.RESOLVED


# --- Autenticación y permisos --------------------------------------------------------


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("get", "/mis-solicitudes"),
        ("get", "/mis-solicitudes/SIG-0001"),
        ("post", "/mis-solicitudes/SIG-0002/confirmar"),
    ],
)
def test_sin_sesion_responde_401(entorno, metodo, ruta) -> None:
    maker, _ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    try:
        respuesta = getattr(TestClient(fastapi_app), metodo)(ruta)
    finally:
        fastapi_app.dependency_overrides.clear()

    assert respuesta.status_code == 401


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("get", "/mis-solicitudes"),
        ("get", "/mis-solicitudes/SIG-0001"),
        ("post", "/mis-solicitudes/SIG-0002/confirmar"),
    ],
)
def test_un_support_agent_sin_el_permiso_responde_403(cliente, metodo, ruta) -> None:
    client, maker, ids = cliente
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como(
        ids["solicitante"], "support_agent"
    )

    respuesta = getattr(client, metodo)(ruta)

    assert respuesta.status_code == 403
    assert _leer(maker, "SIG-0002").status == RequestStatus.RESOLVED


def test_el_permiso_de_consulta_propia_es_del_solicitante_y_del_administrador() -> None:
    assert has_permission(RoleName.REQUESTER, Permission.REQUESTS_VIEW_OWN)
    assert has_permission(RoleName.ADMINISTRATOR, Permission.REQUESTS_VIEW_OWN)
    assert not has_permission(RoleName.SUPPORT_AGENT, Permission.REQUESTS_VIEW_OWN)


def test_fecha_compromiso_vive_en_el_reloj_del_sla_y_sigue_disponible_en_avisos() -> None:
    assert notificacion_service.fecha_compromiso is sla_clock_service.fecha_compromiso
