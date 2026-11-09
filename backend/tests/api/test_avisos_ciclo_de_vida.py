"""Pruebas de API de los avisos del ciclo de vida de una solicitud (S4-07, HU-07.1).

- Registrar, resolver y confirmar una solicitud generan sus avisos, y cada aviso queda
  en `/notificaciones` del destinatario en cuanto termina la acción («menos de un minuto»).
- El aviso de alta trae la categoría, la prioridad y la fecha compromiso reales que deja
  la clasificación (con la versión del acuerdo de S4-13), no «—».
- Quien no es destinatario no ve el aviso.
- Ningún evento avisa dos veces a la misma persona.
- Si la escritura del aviso falla, el alta no se guarda.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.api.routers.solicitudes import get_clasificacion_service
from app.db.base import Base
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models.catalog import AreaServicio, Categoria
from app.models.enums import ClassificationSource, Priority, RequestStatus, UserType
from app.models.identity import User
from app.models.notification import Notification
from app.models.organization import OrganizationalUnit
from app.models.request import Request, RequestAssignment
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.repositories.notificacion_repository import NotificacionRepository
from app.services.clasificacion_service import ClasificacionService

TEXTO_CLARO = {
    "title": "No hay internet",
    "description": "El wifi del edificio no tiene conexion",
}
RESOLUCION_MINUTOS = {Priority.P1: 120, Priority.P2: 240, Priority.P3: 480, Priority.P4: 960}


class ClasificadorFalso:
    """Clasificador con una predicción fija de «Redes», para controlar la confianza."""

    fuente = ClassificationSource.MODEL
    exactitud = 0.9
    artefacto = None
    entrenado_en = datetime(2026, 10, 1, tzinfo=UTC)
    version = "falso-v1"

    def __init__(self, confianza: float) -> None:
        self.confianza = confianza

    def predecir(self, texto: str):
        from app.integrations.clasificador_client import Prediccion

        return Prediccion(
            categoria="Redes",
            urgencia=3,
            impacto=3,
            confianza=self.confianza,
            fuente=self.fuente,
            version=self.version,
        )


class ClasificadorRoto(ClasificadorFalso):
    def __init__(self) -> None:
        super().__init__(confianza=0.0)

    def predecir(self, texto: str):
        raise RuntimeError("el modelo no cargó")


def _user(user_id: uuid.UUID, institutional_id: str, nombre: str) -> User:
    return User(
        id=user_id,
        institutional_id=institutional_id,
        full_name=nombre,
        email=f"{institutional_id}@example.test",
        user_type=UserType.ACADEMIC,
        is_active=True,
    )


def _como(user_id: uuid.UUID, role: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name=role))],
    )


@pytest.fixture
def entorno():
    """SQLite con catálogo, acuerdo predeterminado para cada prioridad y tres personas."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"tecnico": uuid.uuid4(), "solicitante": uuid.uuid4(), "otra": uuid.uuid4()}

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            unidad = OrganizationalUnit(name="Facultad de prueba", unit_type="facultad")
            session.add(unidad)
            await session.flush()
            area = AreaServicio(unit_id=unidad.id, name="Soporte")
            session.add(area)
            await session.flush()
            for nombre in ("Hardware", "Software", "Redes", "Cuentas y accesos"):
                categoria = Categoria(area_id=area.id, name=nombre)
                session.add(categoria)
                await session.flush()
                ids[nombre] = categoria.id
            acuerdo = ServiceLevelAgreement(name="Acuerdo general", is_default=True)
            session.add(acuerdo)
            await session.flush()
            for prioridad, minutos in RESOLUCION_MINUTOS.items():
                session.add(
                    ServiceLevelVersion(
                        agreement_id=acuerdo.id,
                        version=1,
                        priority=prioridad,
                        first_response_minutes=30,
                        resolution_minutes=minutos,
                        valid_from=datetime(2020, 1, 1, tzinfo=UTC),
                    )
                )
            session.add_all(
                [
                    _user(ids["tecnico"], "tec-001", "Tomás Técnico"),
                    _user(ids["solicitante"], "sol-001", "Sara Solicitante"),
                    _user(ids["otra"], "otr-001", "Olga Otra"),
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
    """Cliente HTTP con clasificador falso de confianza alta; `como(rol, persona)` cambia
    el usuario en sesión y `usar(clasificador)` reemplaza el clasificador del alta."""
    maker, ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    def como(rol: str, persona: str = "solicitante") -> TestClient:
        fastapi_app.dependency_overrides[get_current_user] = lambda: _como(ids[persona], rol)
        return client

    def usar(clasificador) -> None:
        def servicio(session: AsyncSession = Depends(get_session)) -> ClasificacionService:
            return ClasificacionService(session, clasificador=clasificador)

        fastapi_app.dependency_overrides[get_clasificacion_service] = servicio

    fastapi_app.dependency_overrides[get_session] = sesion
    client = TestClient(fastapi_app, raise_server_exceptions=False)
    usar(ClasificadorFalso(confianza=0.95))
    try:
        yield SimpleNamespace(como=como, usar=usar, maker=maker, ids=ids)
    finally:
        fastapi_app.dependency_overrides.clear()


def _correr(maker, escenario):
    async def correr():
        async with maker() as session:
            return await escenario(session)

    return asyncio.run(correr())


def _alta(cliente, **cambios) -> dict:
    cuerpo = {
        "requester_id": str(cliente.ids["solicitante"]),
        "physical_location": "Edificio A, laboratorio 2",
        **TEXTO_CLARO,
        **cambios,
    }
    respuesta = cliente.como("requester").post("/solicitudes", json=cuerpo)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _alta_asistida(cliente, **cambios) -> dict:
    cuerpo = {
        "requester_institutional_id": "sol-001",
        "physical_location": "Edificio A, laboratorio 2",
        "channel": "phone",
        **TEXTO_CLARO,
        **cambios,
    }
    respuesta = cliente.como("support_agent", "tecnico").post("/solicitudes/asistido", json=cuerpo)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _bandeja(cliente, persona: str) -> list[dict]:
    respuesta = cliente.como("requester", persona).get("/notificaciones")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _asignar(cliente, request_id: str) -> None:
    """Asigna la solicitud al técnico: aún no hay endpoint de asignación (Sprint 5)."""

    async def asignar(session):
        request = await session.get(Request, uuid.UUID(request_id))
        request.status = RequestStatus.ASSIGNED
        session.add(
            RequestAssignment(
                request_id=request.id,
                technician_id=cliente.ids["tecnico"],
                assigned_at=datetime.now(UTC),
            )
        )
        await session.commit()

    _correr(cliente.maker, asignar)


def _fecha_compromiso_esperada(cliente, request_id: str) -> str:
    """Alta + minutos de resolución de la versión asignada, como la muestra el aviso."""

    async def leer(session):
        result = await session.scalars(
            select(Request)
            .where(Request.id == uuid.UUID(request_id))
            .options(selectinload(Request.service_level_version))
        )
        return result.one()

    request = _correr(cliente.maker, leer)
    assert request.service_level_version is not None, "la solicitud no tiene acuerdo asignado"
    creada = request.created_at.replace(tzinfo=UTC)
    fecha = creada + timedelta(minutes=request.service_level_version.resolution_minutes)
    return fecha.strftime("%d/%m/%Y %H:%M UTC")


def _total_avisos(cliente) -> int:
    async def contar(session):
        return await session.scalar(select(func.count()).select_from(Notification))

    return _correr(cliente.maker, contar)


# ------------------------------------------------ registrar, resolver, confirmar


def test_registrar_resolver_y_confirmar_generan_sus_avisos(cliente):
    solicitud = _alta(cliente)
    assert solicitud["status"] == "classified"

    # Alta: el aviso ya está en la bandeja del solicitante al responder el alta.
    bandeja = _bandeja(cliente, "solicitante")
    assert [a["subject"] for a in bandeja] == ["Solicitud SIG-0001 registrada"]
    alta = bandeja[0]
    assert alta["request_folio"] == "SIG-0001"
    assert alta["is_read"] is False
    fecha = _fecha_compromiso_esperada(cliente, solicitud["id"])
    for dato in ("SIG-0001", "Redes", solicitud["priority"], fecha):
        assert dato in alta["body"], f"falta «{dato}» en {alta['body']!r}"
    assert "Fecha compromiso: —" not in alta["body"]

    # Resolver (el técnico) -> `request_resolved` al solicitante.
    _asignar(cliente, solicitud["id"])
    resuelta = cliente.como("support_agent", "tecnico").post(
        f"/solicitudes/{solicitud['id']}/resolver", json={"solution": "Se reinició el AP."}
    )
    assert resuelta.status_code == 200, resuelta.text
    bandeja = _bandeja(cliente, "solicitante")
    assert bandeja[0]["subject"] == "Solicitud SIG-0001 resuelta"
    for dato in ("Redes", "Tomás Técnico", fecha):
        assert dato in bandeja[0]["body"]

    # Confirmar (el solicitante) -> `request_closed` al solicitante y al técnico.
    cerrada = cliente.como("requester").post("/mis-solicitudes/SIG-0001/confirmar")
    assert cerrada.status_code == 200, cerrada.text
    assert [a["subject"] for a in _bandeja(cliente, "solicitante")] == [
        "Solicitud SIG-0001 cerrada",
        "Solicitud SIG-0001 resuelta",
        "Solicitud SIG-0001 registrada",
    ]
    tecnico = _bandeja(cliente, "tecnico")
    assert [a["subject"] for a in tecnico] == ["Solicitud SIG-0001 cerrada"]
    assert fecha in tecnico[0]["body"]

    contador = cliente.como("requester", "solicitante").get("/notificaciones/contador")
    assert contador.json() == {"unread": 3}


def test_quien_no_es_destinatario_no_ve_el_aviso(cliente):
    _alta(cliente)
    aviso = _bandeja(cliente, "solicitante")[0]

    assert _bandeja(cliente, "otra") == []
    assert _bandeja(cliente, "tecnico") == []
    contador = cliente.como("requester", "otra").get("/notificaciones/contador")
    assert contador.json() == {"unread": 0}
    ajena = cliente.como("requester", "otra").post(f"/notificaciones/{aviso['id']}/leer")
    assert ajena.status_code == 404


# ---------------------------------------------------------- variantes del alta


def test_el_registro_asistido_avisa_al_solicitante_y_no_al_tecnico_que_captura(cliente):
    solicitud = _alta_asistida(cliente)

    bandeja = _bandeja(cliente, "solicitante")
    assert [a["subject"] for a in bandeja] == ["Solicitud SIG-0001 registrada"]
    assert _fecha_compromiso_esperada(cliente, solicitud["id"]) in bandeja[0]["body"]
    assert _bandeja(cliente, "tecnico") == []


def test_un_alta_por_revisar_avisa_una_sola_vez(cliente):
    cliente.usar(ClasificadorFalso(confianza=0.2))

    solicitud = _alta(cliente)

    assert solicitud["status"] == "pending_review"
    assert [a["subject"] for a in _bandeja(cliente, "solicitante")] == [
        "Solicitud SIG-0001 registrada"
    ]
    assert _total_avisos(cliente) == 1


def test_si_el_clasificador_falla_el_alta_avisa_una_sola_vez(cliente):
    cliente.usar(ClasificadorRoto())

    solicitud = _alta(cliente)

    assert solicitud["status"] == "registered"
    assert [a["subject"] for a in _bandeja(cliente, "solicitante")] == [
        "Solicitud SIG-0001 registrada"
    ]
    assert _total_avisos(cliente) == 1


def test_un_solicitante_por_verificar_no_genera_avisos(cliente):
    solicitud = _alta_asistida(cliente, requester_institutional_id="desconocido-99")

    assert solicitud["status"] == "pending_verification"
    assert _total_avisos(cliente) == 0


# --------------------------------------------------------------- transacción


def test_si_falla_la_escritura_del_aviso_el_alta_no_se_guarda(cliente, monkeypatch):
    async def falla(self, avisos):
        raise RuntimeError("no se pudo escribir el aviso")

    monkeypatch.setattr(NotificacionRepository, "add_many", falla)
    cuerpo = {
        "requester_id": str(cliente.ids["solicitante"]),
        "physical_location": "Edificio A, laboratorio 2",
        **TEXTO_CLARO,
    }

    respuesta = cliente.como("requester").post("/solicitudes", json=cuerpo)

    assert respuesta.status_code == 500

    async def contar(session):
        return await session.scalar(select(func.count()).select_from(Request))

    assert _correr(cliente.maker, contar) == 0
    assert _total_avisos(cliente) == 0


def test_si_falla_el_aviso_de_resolucion_la_solicitud_no_se_resuelve(cliente, monkeypatch):
    solicitud = _alta(cliente)
    _asignar(cliente, solicitud["id"])

    async def falla(self, avisos):
        raise RuntimeError("no se pudo escribir el aviso")

    monkeypatch.setattr(NotificacionRepository, "add_many", falla)

    respuesta = cliente.como("support_agent", "tecnico").post(
        f"/solicitudes/{solicitud['id']}/resolver", json={"solution": "Se reinició el AP."}
    )

    assert respuesta.status_code == 500

    async def leer(session):
        return await session.get(Request, uuid.UUID(solicitud["id"]))

    assert _correr(cliente.maker, leer).status == RequestStatus.ASSIGNED
