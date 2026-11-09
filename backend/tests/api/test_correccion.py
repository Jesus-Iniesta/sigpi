"""Pruebas del registro de correcciones como ejemplos (S4-16, HU-02.2 AC2).

- Sin justificación, `POST /revision/{result_id}/correccion` responde 422 con error por
  campo en español (COR-07).
- Con justificación, la prioridad se recalcula (RN-05), la solicitud pasa a «Clasificada»
  y queda una corrección guardada, con bitácora y auditoría en la misma transacción.
- Una segunda corrección del mismo resultado, o la de un resultado que ya no está «Por
  revisar», responde 409.
- La exportación produce filas con las columnas de `dataset_v1.csv`.
"""

import asyncio
import csv
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.core.permissions import RoleName
from app.db.base import Base
from app.db.session import get_session
from app.domain.auditoria import AuditContext
from app.main import app as fastapi_app
from app.models.auditoria import Auditoria
from app.models.catalog import Categoria
from app.models.classification import ClassificationCorrection, ClassificationResult
from app.models.enums import (
    ClassificationSource,
    Priority,
    RequestChannel,
    RequestStatus,
    UserType,
)
from app.models.identity import User
from app.models.request import Request, RequestLog
from app.repositories.correccion_repository import CorreccionRepository, EjemploCorregido
from app.schemas.revision import RevisionInput, RevisionResult
from app.services.auditoria_service import AuditoriaService
from app.services.clasificacion_service import texto_de
from app.services.revision_service import ACCION_CORREGIDA, RevisionService

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from ml.etl.build_dataset import COLUMNAS, RUTA_SALIDA, escribir_csv
from ml.etl.exportar_correcciones import FUENTE, construir_filas

INICIO = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
REVISION_TS = RAIZ / "frontend" / "src" / "api" / "revision.ts"
JUSTIFICACION = "Es un problema de cuenta, no de red."


# ---------------------------------------------------------- contrato con el frontend


def _campos_frontend(tipo: str) -> set[str]:
    texto = REVISION_TS.read_text(encoding="utf-8")
    bloque = re.search(rf"export type {tipo} = \{{(.*?)\n\}}", texto, re.DOTALL)
    assert bloque is not None, f"No se encontró `{tipo}` en revision.ts"
    return set(re.findall(r"^\s*(\w+)\??:", bloque.group(1), re.MULTILINE))


@pytest.mark.parametrize("modelo", [RevisionInput, RevisionResult])
def test_contrato_coincide_campo_por_campo_con_el_frontend(modelo) -> None:
    campos = _campos_frontend(modelo.__name__)
    assert campos
    assert set(modelo.model_fields) == campos


def test_la_justificacion_se_guarda_sin_espacios_al_inicio_o_final() -> None:
    datos = RevisionInput(
        category_id=uuid.uuid4(), urgency=1, impact=1, justification=f"  {JUSTIFICACION}\n"
    )
    assert datos.justification == JUSTIFICACION


# --------------------------------------------------------------------------- entorno


@pytest.fixture
def entorno():
    """Una solicitud «Por revisar» y otra ya «Clasificada», cada una con su resultado."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {
        k: uuid.uuid4()
        for k in (
            "solicitante",
            "revisora",
            "area",
            "redes",
            "cuentas",
            "inactiva",
            "pendiente",
            "lista",
            "resultado",
            "resultado_lista",
        )
    }

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            for key, nombre, correo in (
                ("solicitante", "Sara Solicitante", "sara@example.test"),
                ("revisora", "Rita Revisora", "rita@example.test"),
            ):
                session.add(
                    User(
                        id=ids[key],
                        institutional_id=f"u-{key}",
                        full_name=nombre,
                        email=correo,
                        user_type=UserType.ACADEMIC,
                    )
                )
            session.add_all(
                [
                    Categoria(id=ids["redes"], area_id=ids["area"], name="Redes"),
                    Categoria(id=ids["cuentas"], area_id=ids["area"], name="Cuentas y accesos"),
                    Categoria(
                        id=ids["inactiva"], area_id=ids["area"], name="Antigua", is_active=False
                    ),
                ]
            )
            await session.flush()
            for key, folio, status in (
                ("pendiente", "SIG-0001", RequestStatus.PENDING_REVIEW),
                ("lista", "SIG-0002", RequestStatus.CLASSIFIED),
            ):
                session.add(
                    Request(
                        id=ids[key],
                        requester_id=ids["solicitante"],
                        category_id=ids["redes"],
                        folio=folio,
                        title="No puedo entrar al correo",
                        description="Desde ayer el correo institucional rechaza mi contraseña.",
                        physical_location="Edificio B",
                        channel=RequestChannel.PORTAL,
                        status=status,
                        urgency=1,
                        impact=2,
                        priority=Priority.P3,
                        created_at=INICIO,
                    )
                )
            await session.flush()
            for key, request_key in (("resultado", "pendiente"), ("resultado_lista", "lista")):
                session.add(
                    ClassificationResult(
                        id=ids[key],
                        request_id=ids[request_key],
                        category_id=ids["redes"],
                        source=ClassificationSource.MODEL,
                        confidence=0.6,
                        urgency=1,
                        impact=2,
                        created_at=INICIO + timedelta(minutes=1),
                    )
                )
            await session.commit()

    asyncio.run(preparar())

    async def override_session():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = override_session
    client = TestClient(fastapi_app)

    def como(role: str) -> TestClient:
        fastapi_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=ids["revisora"],
            is_active=True,
            roles=[SimpleNamespace(role=SimpleNamespace(name=role))],
        )
        return client

    def consultar(funcion):
        async def ejecutar():
            async with maker() as session:
                return await funcion(session)

        return asyncio.run(ejecutar())

    try:
        yield SimpleNamespace(como=como, ids=ids, consultar=consultar, maker=maker)
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _corregir(entorno, result_key: str = "resultado", role=RoleName.CLASSIFIER, **cambios):
    cuerpo = {
        "category_id": str(entorno.ids["cuentas"]),
        "urgency": 3,
        "impact": 3,
        "justification": JUSTIFICACION,
        **cambios,
    }
    cuerpo = {k: v for k, v in cuerpo.items() if v is not None}
    return entorno.como(role.value).post(
        f"/revision/{entorno.ids[result_key]}/correccion", json=cuerpo
    )


async def _correcciones(session: AsyncSession) -> list[ClassificationCorrection]:
    return list(await session.scalars(select(ClassificationCorrection)))


# --------------------------------------------------------------- justificación (422)


def _error_de_justificacion(response) -> dict:
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    errores = [e for e in body["detail"] if e["loc"] == ["body", "justification"]]
    assert len(errores) == 1
    return errores[0]


def test_sin_justificacion_responde_422_con_error_por_campo_en_espanol(entorno) -> None:
    error = _error_de_justificacion(_corregir(entorno, justification=None))

    assert error["type"] == "missing"
    assert error["msg"] == "La justificación es obligatoria."
    assert entorno.consultar(_correcciones) == []


@pytest.mark.parametrize("texto", ["", "     ", "\n\t "])
def test_justificacion_vacia_responde_422(entorno, texto: str) -> None:
    error = _error_de_justificacion(_corregir(entorno, justification=texto))

    assert error["msg"] == "La justificación es obligatoria."


def test_justificacion_corta_responde_422_aunque_se_rellene_con_espacios(entorno) -> None:
    error = _error_de_justificacion(_corregir(entorno, justification="   Corto.   "))

    assert error["type"] == "string_too_short"
    assert error["msg"] == "La justificación debe tener al menos 10 caracteres."
    assert error["ctx"] == {"min_length": 10}


# ------------------------------------------------------------- corrección aplicada


def test_con_justificacion_recalcula_la_prioridad_y_deja_la_solicitud_clasificada(
    entorno,
) -> None:
    response = _corregir(entorno, justification=f"  {JUSTIFICACION}  ")

    assert response.status_code == 200
    assert response.json() == {
        "request_id": str(entorno.ids["pendiente"]),
        "status": "classified",
        "priority": "P1",  # urgencia 3 × impacto 3 (RN-05); antes era P3
    }

    solicitud = entorno.consultar(lambda s: s.get(Request, entorno.ids["pendiente"]))
    assert solicitud.status == RequestStatus.CLASSIFIED
    assert solicitud.priority == Priority.P1
    assert (solicitud.category_id, solicitud.urgency, solicitud.impact) == (
        entorno.ids["cuentas"],
        3,
        3,
    )


def test_la_prioridad_la_decide_la_matriz_y_no_el_cliente(entorno) -> None:
    response = _corregir(entorno, urgency=1, impact=1)

    assert response.json()["priority"] == "P4"


def test_queda_una_correccion_guardada_con_quien_corrige(entorno) -> None:
    _corregir(entorno)

    (correccion,) = entorno.consultar(_correcciones)
    assert correccion.result_id == entorno.ids["resultado"]
    assert correccion.corrected_by_id == entorno.ids["revisora"]
    assert correccion.corrected_category_id == entorno.ids["cuentas"]
    assert (correccion.corrected_urgency, correccion.corrected_impact) == (3, 3)
    assert correccion.justification == JUSTIFICACION


def test_deja_entrada_en_la_bitacora_y_registro_de_auditoria(entorno) -> None:
    _corregir(entorno)

    (log,) = entorno.consultar(
        lambda s: s.scalars(
            select(RequestLog).where(RequestLog.request_id == entorno.ids["pendiente"])
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
    assert auditoria.entity_id == str(entorno.ids["pendiente"])
    assert auditoria.old_values["status"] == "pending_review"
    assert auditoria.old_values["priority"] == "P3"
    assert auditoria.new_values["status"] == "classified"
    assert auditoria.new_values["priority"] == "P1"
    assert auditoria.new_values["result_id"] == str(entorno.ids["resultado"])
    assert auditoria.new_values["justification"] == JUSTIFICACION


def test_el_servicio_confirma_la_transaccion(entorno) -> None:
    """Regla 7: el servicio que escribe termina en `commit()`; otra sesión ve el cambio."""

    async def corregir() -> None:
        async with entorno.maker() as session:
            await RevisionService(session).corregir(
                entorno.ids["resultado"],
                RevisionInput(
                    category_id=entorno.ids["cuentas"],
                    urgency=2,
                    impact=2,
                    justification=JUSTIFICACION,
                ),
                AuditContext(actor_id=entorno.ids["revisora"]),
            )

    asyncio.run(corregir())

    assert len(entorno.consultar(_correcciones)) == 1
    solicitud = entorno.consultar(lambda s: s.get(Request, entorno.ids["pendiente"]))
    assert solicitud.status == RequestStatus.CLASSIFIED


def test_si_falla_la_auditoria_no_se_guarda_nada(entorno, monkeypatch) -> None:
    async def fallar(*args, **kwargs):
        raise RuntimeError("auditoría caída")

    monkeypatch.setattr(AuditoriaService, "registrar", fallar)

    async def corregir() -> None:
        async with entorno.maker() as session:
            await RevisionService(session).corregir(
                entorno.ids["resultado"],
                RevisionInput(
                    category_id=entorno.ids["cuentas"],
                    urgency=3,
                    impact=3,
                    justification=JUSTIFICACION,
                ),
                AuditContext(actor_id=entorno.ids["revisora"]),
            )

    with pytest.raises(RuntimeError):
        asyncio.run(corregir())

    assert entorno.consultar(_correcciones) == []
    solicitud = entorno.consultar(lambda s: s.get(Request, entorno.ids["pendiente"]))
    assert solicitud.status == RequestStatus.PENDING_REVIEW
    assert solicitud.priority == Priority.P3


# ----------------------------------------------------------------------- conflictos


def test_una_segunda_correccion_del_mismo_resultado_responde_409(entorno) -> None:
    assert _corregir(entorno).status_code == 200

    response = _corregir(entorno, urgency=1, impact=1)

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"
    assert len(entorno.consultar(_correcciones)) == 1
    solicitud = entorno.consultar(lambda s: s.get(Request, entorno.ids["pendiente"]))
    assert solicitud.priority == Priority.P1


def test_corregir_un_resultado_que_ya_no_esta_por_revisar_responde_409(entorno) -> None:
    response = _corregir(entorno, result_key="resultado_lista")

    assert response.status_code == 409
    assert response.json()["detail"] == "La clasificación ya no está «Por revisar»."
    assert entorno.consultar(_correcciones) == []


def test_resultado_inexistente_responde_404(entorno) -> None:
    entorno.ids["fantasma"] = uuid.uuid4()

    assert _corregir(entorno, result_key="fantasma").status_code == 404


@pytest.mark.parametrize("categoria", ["inactiva", "fantasma"])
def test_categoria_inactiva_o_inexistente_responde_422(entorno, categoria: str) -> None:
    entorno.ids.setdefault("fantasma", uuid.uuid4())

    response = _corregir(entorno, category_id=str(entorno.ids[categoria]))

    assert response.status_code == 422
    assert response.json()["code"] == "business_rule_violation"
    assert entorno.consultar(_correcciones) == []


def test_solicitante_recibe_403(entorno) -> None:
    assert _corregir(entorno, role=RoleName.REQUESTER).status_code == 403


# -------------------------------------------------------------------- exportación


def test_ejemplos_para_reentrenamiento_devuelve_texto_y_etiquetas_corregidas(entorno) -> None:
    _corregir(entorno)

    (ejemplo,) = entorno.consultar(
        lambda s: CorreccionRepository(s).ejemplos_para_reentrenamiento()
    )
    assert ejemplo == EjemploCorregido(
        folio="SIG-0001",
        titulo="No puedo entrar al correo",
        descripcion="Desde ayer el correo institucional rechaza mi contraseña.",
        categoria="Cuentas y accesos",
        urgencia=3,
        impacto=3,
    )


def test_si_hay_varias_correcciones_usa_la_mas_reciente(entorno) -> None:
    async def agregar(session: AsyncSession) -> None:
        for minutos, urgencia in ((5, 1), (10, 2)):
            session.add(
                ClassificationCorrection(
                    result_id=entorno.ids["resultado"],
                    corrected_by_id=entorno.ids["revisora"],
                    corrected_category_id=entorno.ids["redes"],
                    corrected_urgency=urgencia,
                    corrected_impact=1,
                    justification=JUSTIFICACION,
                    created_at=INICIO + timedelta(minutes=minutos),
                )
            )
        await session.commit()

    entorno.consultar(agregar)

    (ejemplo,) = entorno.consultar(
        lambda s: CorreccionRepository(s).ejemplos_para_reentrenamiento()
    )
    assert (ejemplo.categoria, ejemplo.urgencia) == ("Redes", 2)


def test_la_exportacion_produce_filas_con_las_columnas_de_dataset_v1(entorno, tmp_path) -> None:
    _corregir(entorno)
    ejemplos = entorno.consultar(lambda s: CorreccionRepository(s).ejemplos_para_reentrenamiento())
    solicitud = entorno.consultar(lambda s: s.get(Request, entorno.ids["pendiente"]))

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
            "id": "SIG-0001",
            "text": texto_de(solicitud),
            "category": "Cuentas y accesos",
            "urgency": "3",
            "impact": "3",
            "source": "correccion",
        }
    ]
    assert FUENTE == "correccion"
