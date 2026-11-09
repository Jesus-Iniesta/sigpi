"""Asignación de la versión del acuerdo al fijar la prioridad (S4-13 y S4-16, HU-08.1).

- Un alta «Clasificada» queda ligada a la versión vigente (acuerdo de su categoría o, si
  no hay, el predeterminado) y tiene fecha compromiso.
- La corrección de una clasificación también asigna la versión vigente.
- Sin acuerdo vigente, el alta y la corrección no fallan: la solicitud sigue sin versión,
  se registra el evento y queda una entrada en la bitácora.
- El resultado, el estatus y la versión se confirman en una sola transacción (regla 7).
- De extremo a extremo: el monitor del 80 % (S4-08) detecta una solicitud creada por la
  API, sin asignarle la versión a mano.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.api.routers.solicitudes import get_clasificacion_service
from app.db.base import Base
from app.db.session import get_session
from app.integrations.clasificador_client import Prediccion
from app.main import app as fastapi_app
from app.models.catalog import AreaServicio, Categoria
from app.models.classification import ClassificationResult
from app.models.enums import ClassificationSource, Priority, RequestStatus, UserType
from app.models.identity import User
from app.models.organization import OrganizationalUnit
from app.models.request import Request, RequestLog
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.services.clasificacion_service import ClasificacionService
from app.services.sla_monitor_service import SlaMonitorService, registrar_en_log
from app.services.sla_service import ACCION_SIN_ACUERDO, SlaService, as_utc
from app.services.solicitud_service import ACCION_CLASIFICACION

VIGENCIA = datetime(2026, 1, 1, tzinfo=UTC)
# Minutos de resolución del predeterminado por prioridad; los de «Redes» son distintos
# para distinguir qué acuerdo se aplicó.
RESOLUCION_PREDETERMINADO = {Priority.P1: 100, Priority.P2: 200, Priority.P3: 300, Priority.P4: 400}
RESOLUCION_REDES_P1 = 60


class ClasificadorFalso:
    """Propone «Redes» con urgencia 3 e impacto 3 (prioridad P1) y la confianza dada."""

    fuente = ClassificationSource.MODEL
    exactitud = 0.9
    artefacto = None
    entrenado_en = datetime(2026, 10, 1, tzinfo=UTC)
    version = "falso-v1"

    def __init__(self, confianza: float) -> None:
        self.confianza = confianza

    def predecir(self, texto: str) -> Prediccion:
        return Prediccion(
            categoria="Redes",
            urgencia=3,
            impacto=3,
            confianza=self.confianza,
            fuente=self.fuente,
            version=self.version,
        )


def _user(user_id: uuid.UUID, institutional_id: str) -> User:
    return User(
        id=user_id,
        institutional_id=institutional_id,
        full_name=f"Usuario {institutional_id}",
        email=f"{institutional_id}@example.test",
        user_type=UserType.ACADEMIC,
        is_active=True,
    )


def _crear_entorno(*, predeterminado: bool, acuerdo_redes: bool):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids: dict[str, uuid.UUID] = {"solicitante": uuid.uuid4(), "revisora": uuid.uuid4()}

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
            for nombre in ("Redes", "Cuentas y accesos"):
                categoria = Categoria(area_id=area.id, name=nombre)
                session.add(categoria)
                await session.flush()
                ids[nombre] = categoria.id
            session.add_all(
                [_user(ids["solicitante"], "sol-001"), _user(ids["revisora"], "rev-001")]
            )
            if predeterminado:
                acuerdo = ServiceLevelAgreement(name="Acuerdo general", is_default=True)
                session.add(acuerdo)
                await session.flush()
                for prioridad, minutos in RESOLUCION_PREDETERMINADO.items():
                    version = ServiceLevelVersion(
                        agreement_id=acuerdo.id,
                        version=1,
                        priority=prioridad,
                        first_response_minutes=10,
                        resolution_minutes=minutos,
                        valid_from=VIGENCIA,
                    )
                    session.add(version)
                    await session.flush()
                    ids[f"general-{prioridad.value}"] = version.id
            if acuerdo_redes:
                acuerdo = ServiceLevelAgreement(name="Redes", category_id=ids["Redes"])
                session.add(acuerdo)
                await session.flush()
                version = ServiceLevelVersion(
                    agreement_id=acuerdo.id,
                    version=1,
                    priority=Priority.P1,
                    first_response_minutes=5,
                    resolution_minutes=RESOLUCION_REDES_P1,
                    valid_from=VIGENCIA,
                )
                session.add(version)
                await session.flush()
                ids["redes-P1"] = version.id
            await session.commit()

    asyncio.run(preparar())

    async def sesion():
        async with maker() as session:
            yield session

    def como(rol: str, user: str = "solicitante") -> TestClient:
        fastapi_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=ids[user],
            is_active=True,
            roles=[SimpleNamespace(role=SimpleNamespace(name=rol))],
        )
        return client

    def usar(clasificador) -> None:
        def servicio(session: AsyncSession = Depends(get_session)) -> ClasificacionService:
            return ClasificacionService(session, clasificador=clasificador)

        fastapi_app.dependency_overrides[get_clasificacion_service] = servicio

    def consultar(funcion):
        async def ejecutar():
            async with maker() as session:
                return await funcion(session)

        return asyncio.run(ejecutar())

    fastapi_app.dependency_overrides[get_session] = sesion
    client = TestClient(fastapi_app)
    usar(ClasificadorFalso(confianza=0.95))
    return engine, SimpleNamespace(como=como, usar=usar, consultar=consultar, maker=maker, ids=ids)


@pytest.fixture
def con_acuerdo():
    """Acuerdo predeterminado para todas las prioridades; «Redes» no tiene acuerdo propio."""
    engine, entorno = _crear_entorno(predeterminado=True, acuerdo_redes=False)
    try:
        yield entorno
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


@pytest.fixture
def con_acuerdo_de_categoria():
    engine, entorno = _crear_entorno(predeterminado=True, acuerdo_redes=True)
    try:
        yield entorno
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


@pytest.fixture
def sin_acuerdo():
    engine, entorno = _crear_entorno(predeterminado=False, acuerdo_redes=False)
    try:
        yield entorno
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _alta(entorno) -> dict:
    respuesta = entorno.como("requester").post(
        "/solicitudes",
        json={
            "requester_id": str(entorno.ids["solicitante"]),
            "physical_location": "Edificio A, laboratorio 2",
            "title": "No hay internet",
            "description": "El wifi del edificio no tiene conexion",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _solicitud(entorno, request_id: str) -> Request:
    """Lee la solicitud en una sesión nueva: solo ve lo que se confirmó."""
    return entorno.consultar(lambda s: s.get(Request, uuid.UUID(request_id)))


def _bitacora(entorno, request_id: str) -> list[RequestLog]:
    return entorno.consultar(
        lambda s: s.scalars(
            select(RequestLog)
            .where(RequestLog.request_id == uuid.UUID(request_id))
            .order_by(RequestLog.created_at)
        )
    ).all()


def _corregir(entorno, request_id: str, **cambios):
    cola = entorno.como("classifier", "revisora").get("/revision/cola").json()
    (item,) = [i for i in cola if i["request_id"] == request_id]
    cuerpo = {
        "category_id": str(entorno.ids["Cuentas y accesos"]),
        "urgency": 2,
        "impact": 2,
        "justification": "Es un problema de cuenta, no de red.",
        **cambios,
    }
    return entorno.como("classifier", "revisora").post(
        f"/revision/{item['result_id']}/correccion", json=cuerpo
    )


# --- alta clasificada ------------------------------------------------------------------


def test_un_alta_clasificada_tiene_version_y_fecha_compromiso(con_acuerdo):
    datos = _alta(con_acuerdo)

    assert datos["status"] == "classified"
    assert datos["priority"] == "P1"
    request = _solicitud(con_acuerdo, datos["id"])
    assert request.service_level_version_id == con_acuerdo.ids["general-P1"]

    detalle = con_acuerdo.como("requester").get(f"/mis-solicitudes/{datos['folio']}")
    assert detalle.status_code == 200, detalle.text
    esperado = as_utc(request.created_at) + timedelta(
        minutes=RESOLUCION_PREDETERMINADO[Priority.P1]
    )
    assert datetime.fromisoformat(detalle.json()["due_at"]) == esperado


def test_el_acuerdo_de_la_categoria_tiene_preferencia_sobre_el_predeterminado(
    con_acuerdo_de_categoria,
):
    datos = _alta(con_acuerdo_de_categoria)

    request = _solicitud(con_acuerdo_de_categoria, datos["id"])
    assert request.category_id == con_acuerdo_de_categoria.ids["Redes"]
    assert request.service_level_version_id == con_acuerdo_de_categoria.ids["redes-P1"]


def test_un_alta_por_revisar_aun_no_tiene_version(con_acuerdo):
    con_acuerdo.usar(ClasificadorFalso(confianza=0.5))

    datos = _alta(con_acuerdo)

    assert datos["status"] == "pending_review"
    assert _solicitud(con_acuerdo, datos["id"]).service_level_version_id is None


def test_resultado_estatus_y_version_se_confirman_en_una_sola_transaccion(con_acuerdo, monkeypatch):
    """Si falla la asignación de la versión, tampoco queda el resultado ni el estatus."""

    async def fallar(*_args, **_kwargs):
        raise RuntimeError("acuerdos no disponibles")

    monkeypatch.setattr(SlaService, "asignar_version_vigente", fallar)

    datos = _alta(con_acuerdo)

    assert datos["status"] == "registered"
    request = _solicitud(con_acuerdo, datos["id"])
    assert request.status == RequestStatus.REGISTERED
    assert request.service_level_version_id is None
    resultados = con_acuerdo.consultar(
        lambda s: s.scalars(
            select(ClassificationResult).where(ClassificationResult.request_id == request.id)
        )
    ).all()
    assert resultados == []
    assert _bitacora(con_acuerdo, datos["id"]) == []


# --- corrección ------------------------------------------------------------------------


def test_la_correccion_asigna_la_version_vigente(con_acuerdo):
    con_acuerdo.usar(ClasificadorFalso(confianza=0.5))
    datos = _alta(con_acuerdo)

    respuesta = _corregir(con_acuerdo, datos["id"])

    assert respuesta.status_code == 200, respuesta.text
    prioridad = Priority(respuesta.json()["priority"])
    request = _solicitud(con_acuerdo, datos["id"])
    assert request.status == RequestStatus.CLASSIFIED
    assert request.service_level_version_id == con_acuerdo.ids[f"general-{prioridad.value}"]


# --- sin acuerdo vigente ---------------------------------------------------------------


def test_sin_acuerdo_vigente_el_alta_no_falla_y_queda_sin_version(sin_acuerdo, caplog):
    with caplog.at_level(logging.WARNING, logger="sigpi.sla"):
        datos = _alta(sin_acuerdo)

    assert datos["status"] == "classified"
    assert datos["priority"] == "P1"
    request = _solicitud(sin_acuerdo, datos["id"])
    assert request.service_level_version_id is None
    logs = _bitacora(sin_acuerdo, datos["id"])
    assert [log.action for log in logs] == [ACCION_CLASIFICACION, ACCION_SIN_ACUERDO]
    assert logs[1].author_id == sin_acuerdo.ids["solicitante"]
    assert "P1" in logs[1].notes
    assert any(r.getMessage() == "sla_sin_version_vigente" for r in caplog.records)

    detalle = sin_acuerdo.como("requester").get(f"/mis-solicitudes/{datos['folio']}")
    assert detalle.json()["due_at"] is None


def test_sin_acuerdo_vigente_la_correccion_no_falla_y_queda_sin_version(sin_acuerdo, caplog):
    sin_acuerdo.usar(ClasificadorFalso(confianza=0.5))
    datos = _alta(sin_acuerdo)

    with caplog.at_level(logging.WARNING, logger="sigpi.sla"):
        respuesta = _corregir(sin_acuerdo, datos["id"])

    assert respuesta.status_code == 200, respuesta.text
    request = _solicitud(sin_acuerdo, datos["id"])
    assert request.status == RequestStatus.CLASSIFIED
    assert request.service_level_version_id is None
    acciones = [log.action for log in _bitacora(sin_acuerdo, datos["id"])]
    assert acciones[-2:] == ["Clasificación corregida", ACCION_SIN_ACUERDO]
    assert any(r.getMessage() == "sla_sin_version_vigente" for r in caplog.records)


def test_una_version_que_aun_no_entra_en_vigor_no_se_asigna(sin_acuerdo):
    """La versión se resuelve con la fecha de registro, no con una vigencia futura."""

    async def publicar_futura(session: AsyncSession) -> None:
        acuerdo = ServiceLevelAgreement(name="Acuerdo general", is_default=True)
        session.add(acuerdo)
        await session.flush()
        session.add(
            ServiceLevelVersion(
                agreement_id=acuerdo.id,
                version=1,
                priority=Priority.P1,
                first_response_minutes=10,
                resolution_minutes=100,
                valid_from=datetime.now(UTC) + timedelta(days=30),
            )
        )
        await session.commit()

    sin_acuerdo.consultar(publicar_futura)

    datos = _alta(sin_acuerdo)

    assert _solicitud(sin_acuerdo, datos["id"]).service_level_version_id is None


# --- de extremo a extremo con el monitor (S4-08) ----------------------------------------


def test_el_monitor_detecta_una_solicitud_creada_por_la_api(con_acuerdo):
    datos = _alta(con_acuerdo)
    creada = as_utc(_solicitud(con_acuerdo, datos["id"]).created_at)
    resolucion = RESOLUCION_PREDETERMINADO[Priority.P1]

    async def vuelta(ahora: datetime) -> list[uuid.UUID]:
        async with con_acuerdo.maker() as session:
            detectadas = await SlaMonitorService(session).ejecutar_vuelta(
                ahora, al_detectar=registrar_en_log
            )
            return [r.id for r in detectadas]

    # Antes del 80 % no se detecta; al llegar, sí.
    assert asyncio.run(vuelta(creada + timedelta(minutes=resolucion * 0.5))) == []
    detectadas = asyncio.run(vuelta(creada + timedelta(minutes=resolucion * 0.8)))

    assert detectadas == [uuid.UUID(datos["id"])]
    assert _solicitud(con_acuerdo, datos["id"]).sla_risk_alerted_at is not None
