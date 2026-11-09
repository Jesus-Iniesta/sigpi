"""Pruebas de la clasificación automática durante el alta (S4-13, HU-02.1 AC1 y AC2).

- Un alta con texto claro queda «Clasificada» con prioridad en menos de cinco segundos.
- Un alta con confianza baja queda «Por revisar», sin categoría aplicada, y aparece en
  `/revision/cola`.
- Si el clasificador lanza una excepción, el alta responde 201 y queda «Registrada».
- El registro asistido respeta la urgencia y el impacto que capturó el técnico.
- `GET /solicitudes/{id}` devuelve la categoría propuesta, la confianza y la versión.

Las pruebas de AC1 y AC2 usan el clasificador real (`nb-v1`); las demás, uno falso para
controlar la confianza.
"""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
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
from app.main import app as fastapi_app
from app.models.catalog import AreaServicio, Categoria
from app.models.classification import ClassificationResult
from app.models.enums import ClassificationSource, RequestStatus, UserType
from app.models.identity import User
from app.models.organization import OrganizationalUnit
from app.models.request import Request, RequestLog
from app.services.clasificacion_service import ClasificacionService
from app.services.sla_service import ACCION_SIN_ACUERDO
from app.services.solicitud_service import ACCION_CLASIFICACION

TEXTO_CLARO = {
    "title": "No hay internet",
    "description": "El wifi del edificio no tiene conexion",
}
TEXTO_VAGO = {"title": "Ayuda", "description": "algo pasa"}


class ClasificadorFalso:
    """Clasificador con una predicción fija, para controlar la confianza."""

    fuente = ClassificationSource.MODEL
    exactitud = 0.9
    artefacto = None
    entrenado_en = datetime(2026, 10, 1, tzinfo=UTC)

    def __init__(self, confianza: float, version: str = "falso-v1") -> None:
        self.confianza = confianza
        self.version = version

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


class ClasificadorRoto:
    version = "roto-v1"
    fuente = ClassificationSource.MODEL
    exactitud = None
    artefacto = None
    entrenado_en = datetime(2026, 10, 1, tzinfo=UTC)

    def predecir(self, texto: str):
        raise RuntimeError("el modelo no cargó")


def _user(user_id: uuid.UUID, institutional_id: str) -> User:
    return User(
        id=user_id,
        institutional_id=institutional_id,
        full_name=f"Usuario {institutional_id}",
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
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"tecnico": uuid.uuid4(), "solicitante": uuid.uuid4()}

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
            session.add_all(
                [_user(ids["tecnico"], "tec-001"), _user(ids["solicitante"], "sol-001")]
            )
            await session.commit()

    asyncio.run(preparar())
    try:
        yield maker, ids
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
def cliente(entorno):
    """Cliente HTTP; `como(rol)` cambia el usuario en sesión y `usar(clasificador)`
    reemplaza el clasificador del alta (por omisión se usa el real, `nb-v1`)."""
    maker, ids = entorno

    async def sesion():
        async with maker() as session:
            yield session

    def como(rol: str, user: str = "tecnico") -> TestClient:
        fastapi_app.dependency_overrides[get_current_user] = lambda: _como(ids[user], rol)
        return client

    def usar(clasificador) -> None:
        def servicio(session: AsyncSession = Depends(get_session)) -> ClasificacionService:
            return ClasificacionService(session, clasificador=clasificador)

        fastapi_app.dependency_overrides[get_clasificacion_service] = servicio

    fastapi_app.dependency_overrides[get_session] = sesion
    client = TestClient(fastapi_app)
    try:
        yield SimpleNamespace(como=como, usar=usar, maker=maker, ids=ids)
    finally:
        fastapi_app.dependency_overrides.clear()


def _cuerpo(ids, **cambios) -> dict:
    cuerpo = {
        "requester_id": str(ids["solicitante"]),
        "physical_location": "Edificio A, laboratorio 2",
        **TEXTO_CLARO,
    }
    cuerpo.update(cambios)
    return cuerpo


def _cuerpo_asistido(**cambios) -> dict:
    cuerpo = {
        "requester_institutional_id": "sol-001",
        "physical_location": "Edificio A, laboratorio 2",
        "channel": "phone",
        **TEXTO_CLARO,
    }
    cuerpo.update(cambios)
    return cuerpo


def _leer(maker, request_id: str) -> tuple[Request, list[RequestLog], list[ClassificationResult]]:
    """Lee la solicitud en una sesión nueva: solo ve lo que se confirmó (regla 7)."""

    async def leer():
        async with maker() as session:
            request = await session.get(Request, uuid.UUID(request_id))
            logs = list(
                await session.scalars(
                    select(RequestLog)
                    .where(RequestLog.request_id == request.id)
                    .order_by(RequestLog.created_at)
                )
            )
            resultados = list(
                await session.scalars(
                    select(ClassificationResult).where(
                        ClassificationResult.request_id == request.id
                    )
                )
            )
            return request, logs, resultados

    return asyncio.run(leer())


# --- AC1: texto claro -> «Clasificada» con prioridad ----------------------------------


def test_un_alta_con_texto_claro_queda_clasificada_con_prioridad_en_menos_de_5s(cliente):
    inicio = time.perf_counter()
    respuesta = cliente.como("requester", "solicitante").post(
        "/solicitudes", json=_cuerpo(cliente.ids)
    )
    duracion = time.perf_counter() - inicio

    assert respuesta.status_code == 201, respuesta.text
    assert duracion < 5
    datos = respuesta.json()
    assert datos["status"] == "classified"
    assert datos["category_id"] == str(cliente.ids["Redes"])
    assert datos["urgency"] is not None and datos["impact"] is not None
    assert datos["priority"] is not None
    assert datos["classification_confidence"] >= 0.75


def test_la_clasificacion_se_confirma_y_deja_entrada_en_la_bitacora(cliente):
    respuesta = cliente.como("requester", "solicitante").post(
        "/solicitudes", json=_cuerpo(cliente.ids)
    )

    request, logs, resultados = _leer(cliente.maker, respuesta.json()["id"])
    assert request.status == RequestStatus.CLASSIFIED
    assert request.priority is not None
    assert len(resultados) == 1
    # Este entorno no tiene acuerdo de nivel de servicio: la bitácora lo registra (S4-13).
    assert [log.action for log in logs] == [ACCION_CLASIFICACION, ACCION_SIN_ACUERDO]
    entrada = logs[0]
    assert entrada.author_id == cliente.ids["solicitante"]
    assert entrada.previous_status == RequestStatus.REGISTERED
    assert entrada.new_status == RequestStatus.CLASSIFIED
    assert "nb-v1" in entrada.notes
    assert "Confianza" in entrada.notes


# --- AC2: confianza baja -> «Por revisar» y en la cola ---------------------------------


def test_un_alta_con_confianza_baja_queda_por_revisar_y_aparece_en_la_cola(cliente):
    respuesta = cliente.como("requester", "solicitante").post(
        "/solicitudes", json=_cuerpo(cliente.ids, **TEXTO_VAGO)
    )

    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()
    assert datos["status"] == "pending_review"
    # La propuesta se guarda, pero no se aplica hasta la revisión.
    assert datos["category_id"] is None
    assert datos["urgency"] is None and datos["impact"] is None
    assert datos["priority"] is None
    assert datos["classification_confidence"] < 0.75

    cola = cliente.como("classifier").get("/revision/cola")
    assert cola.status_code == 200
    assert [item["request_id"] for item in cola.json()] == [datos["id"]]

    _request, logs, resultados = _leer(cliente.maker, datos["id"])
    assert len(resultados) == 1
    assert [(log.action, log.new_status) for log in logs] == [
        (ACCION_CLASIFICACION, RequestStatus.PENDING_REVIEW)
    ]


def test_el_umbral_exacto_clasifica_y_uno_menor_manda_a_revision(cliente):
    cliente.usar(ClasificadorFalso(confianza=0.75))
    aceptada = cliente.como("requester", "solicitante").post(
        "/solicitudes", json=_cuerpo(cliente.ids)
    )
    cliente.usar(ClasificadorFalso(confianza=0.7499))
    revisar = cliente.como("requester", "solicitante").post(
        "/solicitudes", json=_cuerpo(cliente.ids)
    )

    assert aceptada.json()["status"] == "classified"
    assert revisar.json()["status"] == "pending_review"


# --- AC3: el clasificador falla -> 201 y «Registrada» ----------------------------------


def test_si_el_clasificador_falla_el_alta_responde_201_y_queda_registrada(cliente, caplog):
    cliente.usar(ClasificadorRoto())

    with caplog.at_level(logging.ERROR, logger="sigpi.solicitudes"):
        respuesta = cliente.como("requester", "solicitante").post(
            "/solicitudes", json=_cuerpo(cliente.ids)
        )

    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()
    assert datos["status"] == "registered"
    assert datos["classification_confidence"] is None
    request, logs, resultados = _leer(cliente.maker, datos["id"])
    assert request.status == RequestStatus.REGISTERED
    assert logs == [] and resultados == []
    assert any(r.getMessage() == "clasificacion_fallida" for r in caplog.records)


def test_si_el_clasificador_falla_el_registro_asistido_conserva_su_bitacora(cliente):
    cliente.usar(ClasificadorRoto())

    respuesta = cliente.como("support_agent").post("/solicitudes/asistido", json=_cuerpo_asistido())

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["status"] == "registered"
    _request, logs, _resultados = _leer(cliente.maker, respuesta.json()["id"])
    assert [log.action for log in logs] == ["Solicitud registrada por teléfono"]


# --- Registro asistido: se respeta lo que capturó el técnico ---------------------------


def test_el_registro_asistido_conserva_la_urgencia_y_el_impacto_del_tecnico(cliente):
    cliente.usar(ClasificadorFalso(confianza=0.95))  # propone urgencia 3, impacto 3

    respuesta = cliente.como("support_agent").post(
        "/solicitudes/asistido", json=_cuerpo_asistido(urgency=1, impact=1)
    )

    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()
    assert datos["status"] == "classified"
    assert datos["category_id"] == str(cliente.ids["Redes"])
    assert (datos["urgency"], datos["impact"], datos["priority"]) == (1, 1, "P4")
    _request, logs, _resultados = _leer(cliente.maker, datos["id"])
    assert [log.action for log in logs] == [
        "Solicitud registrada por teléfono",
        ACCION_CLASIFICACION,
        ACCION_SIN_ACUERDO,
    ]
    assert logs[1].author_id == cliente.ids["tecnico"]


def test_el_registro_asistido_completa_con_el_clasificador_lo_que_falta(cliente):
    cliente.usar(ClasificadorFalso(confianza=0.95))

    respuesta = cliente.como("support_agent").post(
        "/solicitudes/asistido", json=_cuerpo_asistido(urgency=1)
    )

    datos = respuesta.json()
    assert (datos["urgency"], datos["impact"]) == (1, 3)
    assert datos["priority"] is not None


def test_el_alta_del_portal_toma_urgencia_e_impacto_del_clasificador(cliente):
    cliente.usar(ClasificadorFalso(confianza=0.95))

    respuesta = cliente.como("requester", "solicitante").post(
        "/solicitudes", json=_cuerpo(cliente.ids)
    )

    datos = respuesta.json()
    assert (datos["urgency"], datos["impact"], datos["priority"]) == (3, 3, "P1")


def test_una_solicitud_por_verificar_no_se_clasifica(cliente):
    cliente.usar(ClasificadorFalso(confianza=0.95))

    respuesta = cliente.como("support_agent").post(
        "/solicitudes/asistido", json=_cuerpo_asistido(requester_institutional_id="nadie-999")
    )

    assert respuesta.json()["status"] == "pending_verification"
    _request, _logs, resultados = _leer(cliente.maker, respuesta.json()["id"])
    assert resultados == []


# --- AC2 (HU-02.1): el detalle muestra la propuesta ------------------------------------


def test_el_detalle_incluye_categoria_propuesta_confianza_y_version(cliente):
    cliente.usar(ClasificadorFalso(confianza=0.5, version="falso-v2"))
    creada = cliente.como("requester", "solicitante").post(
        "/solicitudes", json=_cuerpo(cliente.ids)
    )

    detalle = cliente.como("support_agent").get(f"/solicitudes/{creada.json()['id']}")

    assert detalle.status_code == 200, detalle.text
    datos = detalle.json()
    assert datos["status"] == "pending_review"
    assert datos["category_id"] is None
    assert datos["proposed_category_id"] == str(cliente.ids["Redes"])
    assert datos["proposed_category_name"] == "Redes"
    assert datos["classification_confidence"] == pytest.approx(0.5)
    assert datos["model_version"] == "falso-v2"


def test_el_detalle_sin_clasificacion_deja_vacios_los_campos(cliente):
    cliente.usar(ClasificadorRoto())
    creada = cliente.como("requester", "solicitante").post(
        "/solicitudes", json=_cuerpo(cliente.ids)
    )

    datos = cliente.como("support_agent").get(f"/solicitudes/{creada.json()['id']}").json()

    assert datos["proposed_category_id"] is None
    assert datos["proposed_category_name"] is None
    assert datos["classification_confidence"] is None
    assert datos["model_version"] is None
