"""Pruebas de extremo a extremo de revisión y corrección (S4-17, HU-02.2 AC1-AC4).

- Alta con clasificador simulado a 0.60 queda «Por revisar» y aparece en la cola;
  a 0.90 no aparece.
- Cambiar el umbral en la configuración de prueba cambia la decisión.
- La corrección exige justificación, recalcula la prioridad, saca la solicitud de la
  cola y deja corrección, bitácora y auditoría en la misma transacción.
- La corrección exportada aparece en el formato de reentrenamiento.

Los clasificadores se simulan para controlar la confianza; las peticiones van por HTTP
contra la aplicación real con la sesión de base de datos sobrelacida (regla 7).
"""

import asyncio
import csv
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
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
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_session
from app.domain.auditoria import AuditContext
from app.integrations.clasificador_client import Prediccion
from app.main import app as fastapi_app
from app.models.auditoria import Auditoria
from app.models.catalog import AreaServicio, Categoria
from app.models.classification import ClassificationCorrection
from app.models.enums import (
    ClassificationSource,
    Priority,
    RequestChannel,
    RequestStatus,
    UserType,
)
from app.models.identity import User
from app.models.organization import OrganizationalUnit
from app.models.request import Request, RequestLog
from app.repositories.correccion_repository import CorreccionRepository
from app.schemas.revision import RevisionInput
from app.services.clasificacion_service import ClasificacionService, texto_de
from app.services.revision_service import ACCION_CORREGIDA, RevisionService

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from ml.etl.build_dataset import COLUMNAS, RUTA_SALIDA, escribir_csv
from ml.etl.exportar_correcciones import construir_filas

JUSTIFICACION = "Es un problema de cuenta, no de red."


class ClasificadorFalso:
    """Clasificador con una predicción fija, para controlar la confianza."""

    fuente = ClassificationSource.MODEL
    exactitud = 0.9
    artefacto = None
    entrenado_en = datetime(2026, 10, 1, tzinfo=UTC)

    def __init__(self, confianza: float, version: str = "falso-v1") -> None:
        self.confianza = confianza
        self.version = version

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


def _sesion(user_id: uuid.UUID, role: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        is_active=True,
        roles=[SimpleNamespace(role=SimpleNamespace(name=role))],
    )


@pytest.fixture
def entorno():
    """Organización, área, categorías y dos usuarios; sesión de prueba sobre SQLite."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {
        k: uuid.uuid4()
        for k in ("solicitante", "revisora", "area", "redes", "cuentas")
    }

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
            session.add_all(
                [
                    Categoria(area_id=area.id, name="Redes"),
                    Categoria(area_id=area.id, name="Cuentas y accesos"),
                    _user(ids["solicitante"], "sol-001"),
                    _user(ids["revisora"], "rev-001"),
                ]
            )
            await session.commit()

    asyncio.run(preparar())

    async def categoria_ids() -> dict[str, uuid.UUID]:
        async with maker() as session:
            resultado = await session.execute(select(Categoria))
            return {c.name: c.id for c in resultado.scalars()}

    cats = asyncio.run(categoria_ids())
    ids["redes"] = cats["Redes"]
    ids["cuentas"] = cats["Cuentas y accesos"]

    async def sesion():
        async with maker() as session:
            yield session

    def como(role: str, user: str = "solicitante") -> TestClient:
        fastapi_app.dependency_overrides[get_current_user] = lambda: _sesion(ids[user], role)
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
    try:
        yield SimpleNamespace(como=como, usar=usar, maker=maker, ids=ids, consultar=consultar)
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _cuerpo(ids, **cambios) -> dict:
    cuerpo = {
        "requester_id": str(ids["solicitante"]),
        "physical_location": "Edificio A, laboratorio 2",
        "title": "No puedo entrar al correo institucional",
        "description": "Desde ayer el correo institucional rechaza mi contraseña.",
        "channel": RequestChannel.PORTAL,
    }
    cuerpo.update(cambios)
    return cuerpo


def _result_id_de_cola(entorno, request_id: uuid.UUID) -> uuid.UUID:
    """Devuelve el result_id de la última clasificación de una solicitud en la cola."""
    cola = entorno.como("classifier", "revisora").get("/revision/cola").json()
    for item in cola:
        if item["request_id"] == str(request_id):
            return uuid.UUID(item["result_id"])
    raise AssertionError(f"La solicitud {request_id} no está en la cola de revisión")


# --------------------------------------------------------------- AC1: alta y cola


def test_confianza_0_60_queda_por_revisar_y_aparece_en_la_cola(entorno) -> None:
    entorno.usar(ClasificadorFalso(0.60))
    respuesta = entorno.como("requester").post("/solicitudes", json=_cuerpo(entorno.ids))

    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()
    assert datos["status"] == "pending_review"
    assert datos["classification_confidence"] == pytest.approx(0.60)

    cola = entorno.como("classifier", "revisora").get("/revision/cola")
    assert cola.status_code == 200
    assert [item["request_id"] for item in cola.json()] == [datos["id"]]


def test_confianza_0_90_no_aparece_en_la_cola(entorno) -> None:
    entorno.usar(ClasificadorFalso(0.90))
    respuesta = entorno.como("requester").post("/solicitudes", json=_cuerpo(entorno.ids))

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["status"] == "classified"

    cola = entorno.como("classifier", "revisora").get("/revision/cola").json()
    assert respuesta.json()["id"] not in [item["request_id"] for item in cola]


# ----------------------------------------------------------- AC2: umbral de configuración


def test_cambiar_umbral_cambia_la_decision(entorno, monkeypatch) -> None:
    monkeypatch.setattr(settings, "classification_confidence_threshold", 0.90)
    entorno.usar(ClasificadorFalso(0.80))

    respuesta = entorno.como("requester").post("/solicitudes", json=_cuerpo(entorno.ids))

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["status"] == "pending_review"


# --------------------------------------------------------------- AC3: corrección


def test_correccion_exige_justificacion(entorno) -> None:
    entorno.usar(ClasificadorFalso(0.60))
    creada = entorno.como("requester").post("/solicitudes", json=_cuerpo(entorno.ids))
    result_id = _result_id_de_cola(entorno, uuid.UUID(creada.json()["id"]))

    response = entorno.como("classifier", "revisora").post(
        f"/revision/{result_id}/correccion",
        json={"category_id": str(entorno.ids["cuentas"]), "urgency": 3, "impact": 3},
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"
    assert entorno.consultar(lambda s: s.scalars(select(ClassificationCorrection))).all() == []


def test_correccion_recalcula_prioridad_saca_de_cola_y_deja_rastro(entorno) -> None:
    entorno.usar(ClasificadorFalso(0.60))
    creada = entorno.como("requester").post("/solicitudes", json=_cuerpo(entorno.ids))
    request_id = uuid.UUID(creada.json()["id"])
    result_id = _result_id_de_cola(entorno, request_id)

    response = entorno.como("classifier", "revisora").post(
        f"/revision/{result_id}/correccion",
        json={
            "category_id": str(entorno.ids["cuentas"]),
            "urgency": 3,
            "impact": 3,
            "justification": JUSTIFICACION,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "request_id": str(request_id),
        "status": "classified",
        "priority": "P1",  # urgencia 3 × impacto 3 (RN-05)
    }

    # Sale de la cola de revisión.
    cola = entorno.como("classifier", "revisora").get("/revision/cola").json()
    assert request_id not in [uuid.UUID(item["request_id"]) for item in cola]

    solicitud = entorno.consultar(lambda s: s.get(Request, request_id))
    assert solicitud.status == RequestStatus.CLASSIFIED
    assert solicitud.priority == Priority.P1
    assert (solicitud.category_id, solicitud.urgency, solicitud.impact) == (
        entorno.ids["cuentas"],
        3,
        3,
    )

    (correccion,) = entorno.consultar(lambda s: s.scalars(select(ClassificationCorrection)))
    assert correccion.result_id == result_id
    assert correccion.corrected_by_id == entorno.ids["revisora"]
    assert correccion.justification == JUSTIFICACION

    (log,) = entorno.consultar(
        lambda s: s.scalars(
            select(RequestLog).where(
                RequestLog.request_id == request_id,
                RequestLog.action == "Clasificación corregida",
            )
        )
    )
    assert log.author_id == entorno.ids["revisora"]
    assert log.previous_status == RequestStatus.PENDING_REVIEW
    assert log.new_status == RequestStatus.CLASSIFIED
    assert log.notes == JUSTIFICACION

    (auditoria,) = entorno.consultar(
        lambda s: s.scalars(select(Auditoria).where(Auditoria.action == ACCION_CORREGIDA))
    )
    assert auditoria.actor_id == entorno.ids["revisora"]
    assert auditoria.entity_id == str(request_id)
    assert auditoria.old_values["status"] == "pending_review"
    assert auditoria.new_values["status"] == "classified"
    assert auditoria.new_values["priority"] == "P1"
    assert auditoria.new_values["justification"] == JUSTIFICACION


def test_el_servicio_confirma_la_transaccion_en_la_correccion(entorno) -> None:
    """Regla 7: el servicio confirma la transacción; otra sesión ve el cambio."""
    entorno.usar(ClasificadorFalso(0.60))
    creada = entorno.como("requester").post("/solicitudes", json=_cuerpo(entorno.ids))
    result_id = _result_id_de_cola(entorno, uuid.UUID(creada.json()["id"]))

    async def corregir() -> None:
        async with entorno.maker() as session:
            await RevisionService(session).corregir(
                result_id,
                RevisionInput(
                    category_id=entorno.ids["cuentas"],
                    urgency=2,
                    impact=2,
                    justification=JUSTIFICACION,
                ),
                AuditContext(actor_id=entorno.ids["revisora"]),
            )

    asyncio.run(corregir())

    assert (
        len(
            entorno.consultar(lambda s: s.scalars(select(ClassificationCorrection))).all()
        )
        == 1
    )
    solicitud = entorno.consultar(lambda s: s.get(Request, uuid.UUID(creada.json()["id"])))
    assert solicitud.status == RequestStatus.CLASSIFIED


# --------------------------------------------------------------- AC4: exportación


def test_correccion_exportada_formato_reentrenamiento(entorno, tmp_path) -> None:
    entorno.usar(ClasificadorFalso(0.60))
    creada = entorno.como("requester").post("/solicitudes", json=_cuerpo(entorno.ids))
    result_id = _result_id_de_cola(entorno, uuid.UUID(creada.json()["id"]))
    entorno.como("classifier", "revisora").post(
        f"/revision/{result_id}/correccion",
        json={
            "category_id": str(entorno.ids["cuentas"]),
            "urgency": 3,
            "impact": 3,
            "justification": JUSTIFICACION,
        },
    )

    solicitud = entorno.consultar(lambda s: s.get(Request, uuid.UUID(creada.json()["id"])))
    ejemplos = entorno.consultar(
        lambda s: CorreccionRepository(s).ejemplos_para_reentrenamiento()
    )
    assert len(ejemplos) == 1

    filas = construir_filas(ejemplos)
    salida = tmp_path / "correcciones.csv"
    escribir_csv(filas, salida)

    with RUTA_SALIDA.open(encoding="utf-8", newline="") as archivo:
        columnas_dataset = next(csv.reader(archivo))
    with salida.open(encoding="utf-8", newline="") as archivo:
        exportadas = list(csv.DictReader(archivo))

    assert list(exportadas[0]) == columnas_dataset == list(COLUMNAS)
    assert exportadas == [
        {
            "id": solicitud.folio,
            "text": texto_de(solicitud),
            "category": "Cuentas y accesos",
            "urgency": "3",
            "impact": "3",
            "source": "correccion",
        }
    ]
