"""Pruebas de la consulta por folio y del cierre por confirmación (S4-03, HU-04.3).

`test_mis_solicitudes.py` (S4-01) ya cubre el camino principal de `/mis-solicitudes`:
lista propia, detalle con bitácora sin notas internas, folio ajeno o inexistente (404),
confirmar una solicitud resuelta, 401 y 403. Aquí van los casos que esa prueba no cubre:

- La nota de la confirmación queda en la bitácora y no se devuelve a quien consulta.
- Confirmar dos veces, o en cualquier estado distinto de «Resuelta», no cambia nada.
- Los límites de las notas (vacías, de más de 500 caracteres, campos desconocidos).
- Lo que se ve después de cerrar, la solicitud sin acuerdo de servicio y la propiedad del
  folio vista desde la otra persona y desde el administrador.
- El flujo completo: el técnico resuelve, la persona consulta y confirma.
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
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.enums import RequestChannel, RequestStatus, UserType
from app.models.identity import User
from app.models.request import Request, RequestLog

NOTA = "La red ya funciona, gracias."
OTROS_ESTADOS = [estado for estado in RequestStatus if estado != RequestStatus.RESOLVED]


def _como(user_id: uuid.UUID, role: str = "requester") -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name=role))],
    )


@pytest.fixture
def entorno():
    """Base SQLite con cuatro personas: dos solicitantes, un técnico y un administrador."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {nombre: uuid.uuid4() for nombre in ("solicitante", "otra", "tecnico", "admin")}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            for nombre, user_id in ids.items():
                session.add(
                    User(
                        id=user_id,
                        institutional_id=f"u-{user_id.hex[:8]}",
                        full_name=f"Persona {nombre}",
                        email=f"{nombre}@example.test",
                        user_type=UserType.ACADEMIC,
                    )
                )
            await session.commit()

    asyncio.run(preparar())
    try:
        yield maker, ids
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
def cliente(entorno):
    """Cliente que actúa como la persona solicitante; `_actuar_como` cambia de persona."""
    maker, ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    _actuar_como(ids["solicitante"])
    try:
        yield TestClient(fastapi_app), maker, ids
    finally:
        fastapi_app.dependency_overrides.clear()


def _actuar_como(user_id: uuid.UUID, role: str = "requester") -> None:
    fastapi_app.dependency_overrides[get_current_user] = lambda: _como(user_id, role)


def _crear(
    maker,
    ids,
    folio: str,
    status: RequestStatus = RequestStatus.RESOLVED,
    dueno: str = "solicitante",
) -> uuid.UUID:
    async def crear() -> uuid.UUID:
        async with maker() as session:
            request = Request(
                requester_id=ids[dueno],
                folio=folio,
                title=f"Solicitud {folio}",
                description="No hay red en el laboratorio.",
                physical_location="Edificio B",
                channel=RequestChannel.PORTAL,
                status=status,
            )
            session.add(request)
            await session.commit()
            return request.id

    return asyncio.run(crear())


def _leer(maker, folio: str) -> Request:
    """Lee la solicitud con una sesión nueva: solo ve lo que quedó confirmado en la base."""

    async def leer() -> Request:
        async with maker() as session:
            return (await session.scalars(select(Request).where(Request.folio == folio))).one()

    return asyncio.run(leer())


def _bitacora(maker, folio: str) -> list[RequestLog]:
    async def leer() -> list[RequestLog]:
        async with maker() as session:
            consulta = (
                select(RequestLog)
                .join(Request, RequestLog.request_id == Request.id)
                .where(Request.folio == folio)
                .order_by(RequestLog.created_at)
            )
            return list((await session.scalars(consulta)).all())

    return asyncio.run(leer())


# --- Cierre por confirmación ---------------------------------------------------------


def test_la_nota_de_la_confirmacion_queda_en_la_bitacora_y_no_se_devuelve(cliente) -> None:
    client, maker, ids = cliente
    _crear(maker, ids, "SIG-0001")

    respuesta = client.post("/mis-solicitudes/SIG-0001/confirmar", json={"notes": NOTA})

    assert respuesta.status_code == 200, respuesta.text
    assert NOTA not in respuesta.text
    (entrada,) = _bitacora(maker, "SIG-0001")
    assert entrada.action == "Solicitud confirmada"
    assert entrada.notes == NOTA
    assert entrada.previous_status == RequestStatus.RESOLVED
    assert entrada.new_status == RequestStatus.CLOSED
    assert entrada.author_id == ids["solicitante"]


def test_confirmar_dos_veces_responde_422_y_no_duplica_la_bitacora(cliente) -> None:
    client, maker, ids = cliente
    _crear(maker, ids, "SIG-0001")

    primera = client.post("/mis-solicitudes/SIG-0001/confirmar", json={})
    segunda = client.post("/mis-solicitudes/SIG-0001/confirmar", json={})

    assert primera.status_code == 200, primera.text
    assert segunda.status_code == 422
    assert segunda.json()["code"] == "business_rule_violation"
    assert len(_bitacora(maker, "SIG-0001")) == 1
    assert _leer(maker, "SIG-0001").status == RequestStatus.CLOSED


@pytest.mark.parametrize("estado", OTROS_ESTADOS, ids=[e.value for e in OTROS_ESTADOS])
def test_confirmar_fuera_del_estado_resuelta_responde_422_y_no_modifica(cliente, estado) -> None:
    client, maker, ids = cliente
    _crear(maker, ids, "SIG-0001", estado)

    respuesta = client.post("/mis-solicitudes/SIG-0001/confirmar", json={})

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "business_rule_violation"
    guardada = _leer(maker, "SIG-0001")
    assert guardada.status == estado
    assert guardada.closed_at is None
    assert _bitacora(maker, "SIG-0001") == []


@pytest.mark.parametrize(
    "cuerpo",
    [{"notes": ""}, {"notes": "x" * 501}, {"comentario": "todo bien"}],
    ids=["notas-vacias", "notas-de-501-caracteres", "campo-desconocido"],
)
def test_confirmar_rechaza_notas_invalidas_y_no_cierra_la_solicitud(cliente, cuerpo) -> None:
    client, maker, ids = cliente
    _crear(maker, ids, "SIG-0001")

    respuesta = client.post("/mis-solicitudes/SIG-0001/confirmar", json=cuerpo)

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "validation_error"
    assert _leer(maker, "SIG-0001").status == RequestStatus.RESOLVED


def test_confirmar_acepta_notas_de_exactamente_500_caracteres(cliente) -> None:
    client, maker, ids = cliente
    _crear(maker, ids, "SIG-0001")

    respuesta = client.post("/mis-solicitudes/SIG-0001/confirmar", json={"notes": "x" * 500})

    assert respuesta.status_code == 200, respuesta.text
    assert _leer(maker, "SIG-0001").status == RequestStatus.CLOSED


def test_tras_confirmar_la_lista_y_la_consulta_la_muestran_cerrada(cliente) -> None:
    client, maker, ids = cliente
    _crear(maker, ids, "SIG-0001")

    client.post("/mis-solicitudes/SIG-0001/confirmar", json={})

    lista = client.get("/mis-solicitudes").json()
    assert [(s["folio"], s["status"]) for s in lista] == [("SIG-0001", "closed")]
    detalle = client.get("/mis-solicitudes/SIG-0001").json()
    assert detalle["status"] == "closed"
    assert detalle["closed_at"] is not None
    assert detalle["log"][-1]["action"] == "Solicitud confirmada"


# --- Consulta por folio --------------------------------------------------------------


def test_sin_acuerdo_de_nivel_de_servicio_no_hay_fecha_compromiso(cliente) -> None:
    client, maker, ids = cliente
    _crear(maker, ids, "SIG-0001", RequestStatus.REGISTERED)

    respuesta = client.get("/mis-solicitudes/SIG-0001")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["due_at"] is None


def test_la_otra_persona_solo_ve_sus_propios_folios(cliente) -> None:
    client, maker, ids = cliente
    _crear(maker, ids, "SIG-0001", dueno="solicitante")
    _crear(maker, ids, "SIG-0002", dueno="otra")
    _actuar_como(ids["otra"])

    propio = client.get("/mis-solicitudes/SIG-0002")
    ajeno = client.get("/mis-solicitudes/SIG-0001")
    confirmar_ajeno = client.post("/mis-solicitudes/SIG-0001/confirmar", json={})

    assert propio.status_code == 200
    assert ajeno.status_code == 404
    assert confirmar_ajeno.status_code == 404
    assert _leer(maker, "SIG-0001").status == RequestStatus.RESOLVED
    assert [s["folio"] for s in client.get("/mis-solicitudes").json()] == ["SIG-0002"]


def test_el_administrador_solo_consulta_sus_propias_solicitudes(cliente) -> None:
    client, maker, ids = cliente
    _crear(maker, ids, "SIG-0001", dueno="solicitante")
    _crear(maker, ids, "SIG-0002", dueno="admin")
    _actuar_como(ids["admin"], "administrator")

    assert client.get("/mis-solicitudes/SIG-0002").status_code == 200
    assert client.get("/mis-solicitudes/SIG-0001").status_code == 404


# --- Flujo completo ------------------------------------------------------------------


def test_el_tecnico_resuelve_la_persona_consulta_y_confirma(cliente) -> None:
    client, maker, ids = cliente
    request_id = _crear(maker, ids, "SIG-0001", RequestStatus.IN_PROGRESS)

    _actuar_como(ids["tecnico"], "support_agent")
    resuelta = client.post(
        f"/solicitudes/{request_id}/resolver", json={"solution": "Se reinició el conmutador."}
    )
    assert resuelta.status_code == 200, resuelta.text

    _actuar_como(ids["solicitante"])
    consulta = client.get("/mis-solicitudes/SIG-0001").json()
    assert consulta["status"] == "resolved"
    assert consulta["resolved_at"] is not None
    assert consulta["closed_at"] is None

    confirmada = client.post("/mis-solicitudes/SIG-0001/confirmar", json={"notes": NOTA})
    assert confirmada.status_code == 200, confirmada.text
    assert confirmada.json()["status"] == "closed"

    _actuar_como(ids["tecnico"], "support_agent")
    acciones = [e["action"] for e in client.get(f"/solicitudes/{request_id}/bitacora").json()]
    assert acciones[-1] == "Solicitud confirmada"
    assert len(acciones) == 2
