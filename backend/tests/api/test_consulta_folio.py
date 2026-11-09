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

Y, con el escenario de extremo a extremo (fixture `escenario`, que parte del alta por API):

- Ciclo completo: alta → iniciar → resolver → consulta por folio → confirmar → «Cerrada».
- La fecha compromiso usa la versión del acuerdo vigente al registrar, aunque después se
  publique otra.

La asignación del técnico y de la versión del SLA aún no tienen endpoint, así que
`Escenario.asignar` hace ese paso directo en la base, con la versión que `SlaRepository`
considera vigente en la fecha de alta.
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
from app.api.routers.solicitudes import get_clasificacion_service
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.catalog import Categoria
from app.models.enums import Priority, RequestChannel, RequestStatus, UserType
from app.models.identity import User
from app.models.request import Request, RequestAssignment, RequestLog
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.repositories.sla_repository import SlaRepository
from app.services.sla_service import as_utc

NOTA = "La red ya funciona, gracias."
OTROS_ESTADOS = [estado for estado in RequestStatus if estado != RequestStatus.RESOLVED]
DIAGNOSTICO = "Diagnóstico interno: el puerto 14 del switch del piso 2 está dañado."
SOLUCION = "Solución interna: se cambió el cable al puerto 15 con la contraseña por defecto."
MINUTOS_V1 = 240
MINUTOS_V2 = 60


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


# --- Escenario de extremo a extremo (parte del alta por API) -------------------------


def _utc(texto: str) -> datetime:
    """Lee una fecha ISO de la API; SQLite la devuelve sin zona, así que se asume UTC."""
    valor = datetime.fromisoformat(texto)
    return valor if valor.tzinfo else valor.replace(tzinfo=UTC)


class Escenario:
    """Base SQLite en memoria con el cliente HTTP y el cambio de usuario en sesión."""

    def __init__(self, maker: async_sessionmaker, ids: dict[str, uuid.UUID]) -> None:
        self.maker = maker
        self.ids = ids
        self.client = TestClient(fastapi_app)

    def como(self, key: str, role: str) -> TestClient:
        fastapi_app.dependency_overrides[get_current_user] = lambda: _como(self.ids[key], role)
        return self.client

    def run(self, coro):
        return asyncio.run(coro)

    # --- pasos del ciclo -------------------------------------------------------------

    def registrar(self) -> dict:
        """Alta en el portal por el solicitante (urgencia 2 × impacto 2 = P2)."""
        respuesta = self.como("solicitante", "requester").post(
            "/solicitudes",
            json={
                "requester_id": str(self.ids["solicitante"]),
                "category_id": str(self.ids["categoria"]),
                "title": "Sin red en el laboratorio",
                "description": "Ningún equipo del laboratorio 3 tiene red.",
                "physical_location": "Edificio B, laboratorio 3",
                "urgency": 2,
                "impact": 2,
            },
        )
        assert respuesta.status_code == 201, respuesta.text
        datos = respuesta.json()
        assert datos["status"] == "registered"
        assert datos["priority"] == "P2"
        return datos

    def asignar(self, request_id: str) -> uuid.UUID:
        """Asigna el técnico y la versión del SLA vigente al registrar; la devuelve."""

        async def asignar() -> uuid.UUID:
            async with self.maker() as session:
                request = await session.get(Request, uuid.UUID(request_id))
                repo = SlaRepository(session)
                acuerdo = await repo.find_default()
                version = await repo.find_effective(
                    acuerdo.id, Priority(request.priority).value, as_utc(request.created_at)
                )
                request.service_level_version_id = version.id
                request.status = RequestStatus.ASSIGNED
                session.add(
                    RequestAssignment(
                        request_id=request.id,
                        technician_id=self.ids["tecnico"],
                        assigned_at=as_utc(request.created_at),
                    )
                )
                await session.commit()
                return version.id

        return self.run(asignar())

    def iniciar_y_resolver(self, request_id: str) -> None:
        tecnico = self.como("tecnico", "support_agent")
        respuesta = tecnico.post(f"/solicitudes/{request_id}/iniciar")
        assert respuesta.status_code == 200, respuesta.text
        respuesta = tecnico.post(
            f"/solicitudes/{request_id}/resolver",
            json={"solution": SOLUCION, "diagnosis": DIAGNOSTICO},
        )
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["status"] == "resolved"

    def hasta_resuelta(self) -> dict:
        datos = self.registrar()
        self.asignar(datos["id"])
        self.iniciar_y_resolver(datos["id"])
        return datos

    # --- lecturas con una sesión nueva (solo ven lo confirmado) ----------------------

    def leer(self, request_id: str) -> Request:
        async def leer() -> Request:
            async with self.maker() as session:
                return await session.get(Request, uuid.UUID(request_id))

        return self.run(leer())

    def bitacora(self, request_id: str) -> list[RequestLog]:
        async def leer() -> list[RequestLog]:
            async with self.maker() as session:
                result = await session.scalars(
                    select(RequestLog)
                    .where(RequestLog.request_id == uuid.UUID(request_id))
                    .order_by(RequestLog.created_at)
                )
                return list(result)

        return self.run(leer())


@pytest.fixture
def escenario():
    """Solicitante, otra persona, técnico, una categoría y el acuerdo predeterminado v1."""
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
                        is_active=True,
                    )
                )
            session.add(Categoria(id=ids["categoria"], area_id=uuid.uuid4(), name="Redes"))
            acuerdo = ServiceLevelAgreement(name="Acuerdo general", is_default=True)
            session.add(acuerdo)
            await session.flush()
            ids["acuerdo"] = acuerdo.id
            session.add(
                ServiceLevelVersion(
                    agreement_id=acuerdo.id,
                    version=1,
                    priority=Priority.P2,
                    first_response_minutes=30,
                    resolution_minutes=MINUTOS_V1,
                    valid_from=datetime.now(UTC) - timedelta(days=30),
                )
            )
            await session.commit()

    asyncio.run(preparar())

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    # S4-13: aquí solo se prueba la consulta y el cierre; la clasificación va en
    # test_alta_clasificada.py.
    fastapi_app.dependency_overrides[get_clasificacion_service] = lambda: None
    try:
        yield Escenario(maker, ids)
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


# --- Extremo a extremo desde el alta --------------------------------------------------


def test_ciclo_completo_alta_iniciar_resolver_consultar_y_confirmar_cierra_la_solicitud(
    escenario,
) -> None:
    alta = escenario.hasta_resuelta()
    folio = alta["folio"]
    solicitante = escenario.como("solicitante", "requester")

    consulta = solicitante.get(f"/mis-solicitudes/{folio}")
    assert consulta.status_code == 200, consulta.text
    detalle = consulta.json()
    assert detalle["status"] == "resolved"
    assert detalle["priority"] == "P2"
    assert detalle["category"] == "Redes"
    assert detalle["technician"] == "Tomás Técnico"
    assert detalle["resolved_at"] is not None
    assert detalle["closed_at"] is None
    assert [e["action"] for e in detalle["log"]] == ["Atención iniciada", "Solicitud resuelta"]

    confirmacion = solicitante.post(f"/mis-solicitudes/{folio}/confirmar", json={})
    assert confirmacion.status_code == 200, confirmacion.text
    cerrada = confirmacion.json()
    assert cerrada["status"] == "closed"
    assert cerrada["closed_at"] is not None
    assert cerrada["log"][-1]["action"] == "Solicitud confirmada"
    assert cerrada["log"][-1]["new_status"] == "closed"

    # Una sesión nueva ve el cierre: el servicio confirmó la transacción (commit).
    guardada = escenario.leer(alta["id"])
    assert guardada.status == RequestStatus.CLOSED
    assert guardada.closed_at is not None
    ultima = escenario.bitacora(alta["id"])[-1]
    assert ultima.author_id == escenario.ids["solicitante"]
    assert ultima.previous_status == RequestStatus.RESOLVED


def test_la_fecha_compromiso_usa_la_version_del_acuerdo_vigente_al_registrar(
    escenario,
) -> None:
    alta = escenario.registrar()
    version_al_registrar = escenario.asignar(alta["id"])
    registrada = as_utc(escenario.leer(alta["id"]).created_at)

    # Después del alta se publica la v2 con otro tiempo de resolución.
    async def publicar_v2() -> uuid.UUID:
        async with escenario.maker() as session:
            v1 = await session.get(ServiceLevelVersion, version_al_registrar)
            cambio = registrada + timedelta(minutes=1)
            v1.valid_to = cambio
            v2 = ServiceLevelVersion(
                agreement_id=escenario.ids["acuerdo"],
                version=2,
                priority=Priority.P2,
                first_response_minutes=15,
                resolution_minutes=MINUTOS_V2,
                valid_from=cambio,
            )
            session.add(v2)
            await session.commit()
            return v2.id

    version_v2 = escenario.run(publicar_v2())

    respuesta = escenario.como("solicitante", "requester").get(f"/mis-solicitudes/{alta['folio']}")
    assert respuesta.status_code == 200, respuesta.text
    due_at = _utc(respuesta.json()["due_at"])

    assert escenario.leer(alta["id"]).service_level_version_id == version_al_registrar
    assert version_al_registrar != version_v2
    assert due_at == registrada + timedelta(minutes=MINUTOS_V1)
    assert due_at != registrada + timedelta(minutes=MINUTOS_V2)
