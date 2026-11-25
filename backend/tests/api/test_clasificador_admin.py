"""Pruebas de la administración del clasificador (S5-06, HU-02.2, HU-12.1, HU-12.2).

- `PUT /clasificador/umbral` cambia la decisión del alta sin reiniciar: con 0.95, una
  confianza de 0.8 va a «Por revisar»; con 0.5, se clasifica sola.
- Un umbral fuera de 0.50–0.95 responde 422 y no cambia nada.
- `GET /clasificador/estado` informa versión, umbral, ejemplos y exactitud.
- Reentrenar con correcciones crea una versión nueva; si la exactitud empeora, no se
  activa y la respuesta lo dice.
- Cada cambio de umbral y cada reentrenamiento quedan en la auditoría.
- Solo `administrator` accede; los demás 403; sin sesión 401. Hay una sola cabeza de
  Alembic.
"""

import asyncio
import csv
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.api.dependencies import get_current_user
from app.api.routers.solicitudes import get_clasificacion_service
from app.core.permissions import Permission, RoleName, has_permission
from app.db.base import Base
from app.db.session import get_session
from app.domain.auditoria import AuditContext
from app.integrations import clasificador_client
from app.integrations.clasificador_client import (
    ClasificadorBayes,
    Prediccion,
    cargar_ejemplos,
    ruta_dataset,
    ruta_dataset_mas_reciente,
)
from app.main import app as fastapi_app
from app.models.app_setting import AppSetting
from app.models.auditoria import Auditoria
from app.models.catalog import AreaServicio, Categoria
from app.models.classification import (
    ClassificationCorrection,
    ClassificationResult,
    ClassifierModel,
)
from app.models.enums import ClassificationSource, RequestChannel, RequestStatus, UserType
from app.models.identity import User
from app.models.organization import OrganizationalUnit
from app.models.request import Request, RequestLog
from app.services import clasificador_admin_service
from app.services.clasificacion_service import ClasificacionService
from app.services.clasificador_admin_service import (
    ACCION_REENTRENADO,
    ACCION_UMBRAL,
    ClasificadorAdminService,
    UmbralFueraDeRangoError,
)
from app.services.solicitud_service import ACCION_CLASIFICACION

BACKEND = Path(__file__).resolve().parents[2]
TEXTO = {"title": "No hay internet", "description": "El wifi del edificio no tiene conexion"}


class ClasificadorFalso:
    """Predicción fija con confianza 0.8, para controlar la decisión del umbral."""

    version = "falso-v1"
    fuente = ClassificationSource.MODEL
    exactitud = 0.9
    artefacto = None
    entrenado_en = datetime(2026, 10, 1, tzinfo=UTC)

    def predecir(self, texto: str) -> Prediccion:
        return Prediccion(
            categoria="Redes",
            urgencia=2,
            impacto=2,
            confianza=0.8,
            fuente=self.fuente,
            version=self.version,
        )


def _usuario(user_id: uuid.UUID, institutional_id: str) -> User:
    return User(
        id=user_id,
        institutional_id=institutional_id,
        full_name=f"Usuario {institutional_id}",
        email=f"{institutional_id}@example.test",
        user_type=UserType.ACADEMIC,
        is_active=True,
    )


def _en_sesion(user_id: uuid.UUID, role: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id, is_active=True, roles=[SimpleNamespace(role=SimpleNamespace(name=role))]
    )


@pytest.fixture
def entorno():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {"admin": uuid.uuid4(), "solicitante": uuid.uuid4(), "revisor": uuid.uuid4()}

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
                [
                    _usuario(ids["admin"], "adm-001"),
                    _usuario(ids["solicitante"], "sol-001"),
                    _usuario(ids["revisor"], "rev-001"),
                ]
            )
            await session.commit()

    asyncio.run(preparar())

    async def sesion():
        async with maker() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = sesion
    client = TestClient(fastapi_app)

    def como(rol: str, user: str = "admin") -> TestClient:
        fastapi_app.dependency_overrides[get_current_user] = lambda: _en_sesion(ids[user], rol)
        return client

    def usar(clasificador) -> None:
        def servicio(session: AsyncSession = Depends(get_session)) -> ClasificacionService:
            return ClasificacionService(session, clasificador=clasificador)

        fastapi_app.dependency_overrides[get_clasificacion_service] = servicio

    def correr(fn):
        async def envolver():
            async with maker() as session:
                return await fn(session)

        return asyncio.run(envolver())

    try:
        yield SimpleNamespace(
            como=como, usar=usar, correr=correr, ids=ids, client=client, maker=maker
        )
    finally:
        fastapi_app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def _alta(e) -> dict:
    respuesta = e.como("requester", "solicitante").post(
        "/solicitudes",
        json={
            "requester_id": str(e.ids["solicitante"]),
            "physical_location": "Edificio A",
            **TEXTO,
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _auditoria(e, accion: str) -> list[Auditoria]:
    async def leer(session):
        return list(
            await session.scalars(
                select(Auditoria).where(Auditoria.action == accion).order_by(Auditoria.created_at)
            )
        )

    return e.correr(leer)


def _agregar_correccion(e, categoria: str = "Redes") -> None:
    """Una solicitud corregida por una persona revisora, lista como ejemplo."""

    async def agregar(session):
        request = Request(
            requester_id=e.ids["solicitante"],
            folio=f"SIG-{uuid.uuid4().hex[:6]}",
            title="El wifi del aula no conecta",
            description="Ningún equipo del aula 3 tiene red inalámbrica",
            physical_location="Edificio B",
            channel=RequestChannel.PORTAL,
            status=RequestStatus.CLASSIFIED,
        )
        session.add(request)
        await session.flush()
        resultado = ClassificationResult(
            request_id=request.id,
            source=ClassificationSource.MODEL,
            confidence=0.5,
            urgency=1,
            impact=1,
        )
        session.add(resultado)
        await session.flush()
        session.add(
            ClassificationCorrection(
                result_id=resultado.id,
                corrected_by_id=e.ids["revisor"],
                corrected_category_id=e.ids[categoria],
                corrected_urgency=2,
                corrected_impact=2,
                justification="Es un problema de red.",
            )
        )
        await session.commit()

    e.correr(agregar)


def _dataset(tmp_path: Path, nombre: str, filas: list[tuple[str, str]]) -> Path:
    ruta = tmp_path / nombre
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["id", "text", "category", "urgency", "impact", "source"])
        for i, (texto, categoria) in enumerate(filas):
            escritor.writerow([f"X-{i}", texto, categoria, 2, 2, "prueba"])
    return ruta


# ------------------------------------------------------------------ umbral en caliente


def test_el_umbral_cambia_la_decision_del_alta_sin_reiniciar(entorno) -> None:
    entorno.usar(ClasificadorFalso())

    assert entorno.como("administrator").put(
        "/clasificador/umbral", json={"umbral": 0.95}
    ).json() == {"umbral_anterior": 0.75, "umbral": 0.95}
    assert _alta(entorno)["status"] == RequestStatus.PENDING_REVIEW

    respuesta = entorno.como("administrator").put("/clasificador/umbral", json={"umbral": 0.5})
    assert respuesta.status_code == 200
    assert respuesta.json() == {"umbral_anterior": 0.95, "umbral": 0.5}
    assert _alta(entorno)["status"] == RequestStatus.CLASSIFIED


@pytest.mark.parametrize("valor", [0.49, 0.96, 1.2, -1])
def test_un_umbral_fuera_de_rango_responde_422_y_no_cambia_nada(entorno, valor) -> None:
    respuesta = entorno.como("administrator").put("/clasificador/umbral", json={"umbral": valor})

    assert respuesta.status_code == 422
    assert (
        entorno.correr(lambda s: s.get(AppSetting, "classification_confidence_threshold")) is None
    )
    assert _auditoria(entorno, ACCION_UMBRAL) == []
    assert entorno.como("administrator").get("/clasificador/estado").json()["umbral"] == 0.75


def test_el_servicio_tambien_rechaza_un_umbral_fuera_de_rango(entorno) -> None:
    async def cambiar(session):
        await ClasificadorAdminService(session).cambiar_umbral(0.3, AuditContext())

    with pytest.raises(UmbralFueraDeRangoError):
        entorno.correr(cambiar)


def test_cada_cambio_de_umbral_queda_en_la_auditoria(entorno) -> None:
    admin = entorno.como("administrator")
    admin.put("/clasificador/umbral", json={"umbral": 0.8})
    admin.put("/clasificador/umbral", json={"umbral": 0.6})

    registros = _auditoria(entorno, ACCION_UMBRAL)
    assert [(r.old_values, r.new_values) for r in registros] == [
        ({"umbral": 0.75}, {"umbral": 0.8}),
        ({"umbral": 0.8}, {"umbral": 0.6}),
    ]
    assert all(r.actor_id == entorno.ids["admin"] for r in registros)
    # El ajuste se confirmó: una sesión nueva lo ve.
    ajuste = entorno.correr(lambda s: s.get(AppSetting, "classification_confidence_threshold"))
    assert (ajuste.value, ajuste.updated_by) == ("0.6", entorno.ids["admin"])


# ------------------------------------------------------------------------- estado


def test_el_estado_informa_version_umbral_ejemplos_y_exactitud(entorno) -> None:
    entorno.como("administrator").put("/clasificador/umbral", json={"umbral": 0.7})
    _agregar_correccion(entorno)

    async def bitacora(session):
        hace_mucho = datetime.now(UTC) - timedelta(days=90)
        for estatus, cuando in [
            (RequestStatus.PENDING_REVIEW, None),
            (RequestStatus.CLASSIFIED, None),
            (RequestStatus.CLASSIFIED, None),
            (RequestStatus.CLASSIFIED, None),
            (RequestStatus.PENDING_REVIEW, hace_mucho),  # fuera de la ventana reciente
        ]:
            request = Request(
                folio=f"SIG-{uuid.uuid4().hex[:6]}",
                title="t",
                description="d",
                physical_location="l",
                channel=RequestChannel.PORTAL,
                status=estatus,
            )
            session.add(request)
            await session.flush()
            log = RequestLog(
                request_id=request.id,
                author_id=entorno.ids["solicitante"],
                previous_status=RequestStatus.REGISTERED,
                new_status=estatus,
                action=ACCION_CLASIFICACION,
            )
            if cuando is not None:
                log.created_at = cuando
            session.add(log)
        await session.commit()

    entorno.correr(bitacora)

    respuesta = entorno.como("administrator").get("/clasificador/estado")

    assert respuesta.status_code == 200
    estado = respuesta.json()
    assert estado["version"] == "nb-v1"
    assert estado["umbral"] == 0.7
    assert estado["ejemplos"] == len(cargar_ejemplos(ruta_dataset()))
    assert 0 < estado["exactitud"] <= 1
    assert estado["correcciones_pendientes"] == 1
    assert estado["proporcion_por_revisar"] == 0.25
    assert estado["dias_recientes"] == 30


def test_el_estado_sin_clasificaciones_recientes_no_inventa_proporcion(entorno) -> None:
    estado = entorno.como("administrator").get("/clasificador/estado").json()
    assert estado["proporcion_por_revisar"] is None
    assert estado["correcciones_pendientes"] == 0


# ----------------------------------------------------------------- reentrenamiento


def test_reentrenar_con_correcciones_crea_y_activa_una_version_nueva(entorno, monkeypatch) -> None:
    # El modelo base no se midió: cualquier versión nueva lo mejora.
    monkeypatch.setattr(
        clasificador_admin_service,
        "obtener_clasificador",
        lambda: SimpleNamespace(version="nb-v1", exactitud=None),
    )
    _agregar_correccion(entorno)
    base = len(cargar_ejemplos(ruta_dataset_mas_reciente()))

    respuesta = entorno.como("administrator").post("/clasificador/reentrenar")

    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["version"] == "nb-v2"
    assert datos["activado"] is True
    assert datos["correcciones_incorporadas"] == 1
    assert datos["ejemplos"] == base + 1
    assert 0 < datos["exactitud"] <= 1
    assert "quedó vigente" in datos["mensaje"]

    estado = entorno.como("administrator").get("/clasificador/estado").json()
    assert estado["version"] == "nb-v2"
    assert estado["ejemplos"] == base + 1
    assert estado["exactitud"] == datos["exactitud"]
    assert estado["correcciones_pendientes"] == 0

    # Las solicitudes nuevas usan el modelo vigente, sin reiniciar.
    alta = _alta(entorno)

    async def version_de(session):
        resultado = await session.scalar(
            select(ClassificationResult).where(
                ClassificationResult.request_id == uuid.UUID(alta["id"])
            )
        )
        await session.refresh(resultado, ["model_version"])
        return resultado.model_version.version

    assert entorno.correr(version_de) == "nb-v2"


def test_si_la_exactitud_empeora_la_version_nueva_no_se_activa(
    entorno, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        clasificador_admin_service,
        "obtener_clasificador",
        lambda: SimpleNamespace(version="nb-v1", exactitud=None),
    )
    admin = entorno.como("administrator")
    primera = admin.post("/clasificador/reentrenar").json()
    assert primera["activado"] is True

    # Un conjunto de datos con etiquetas sin relación con el texto empeora la exactitud.
    categorias = ["Hardware", "Software", "Redes", "Cuentas y accesos"]
    ruido = _dataset(
        tmp_path,
        "dataset_v9.csv",
        [(f"texto comun numero {i}", categorias[(i * 7) % 4]) for i in range(40)],
    )
    monkeypatch.setattr(clasificador_admin_service, "ruta_dataset_mas_reciente", lambda: ruido)
    _agregar_correccion(entorno)

    respuesta = admin.post("/clasificador/reentrenar")

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["version"] == "nb-v3"
    assert datos["activado"] is False
    assert datos["version_anterior"] == "nb-v2"
    assert datos["exactitud_anterior"] == primera["exactitud"]
    assert datos["exactitud"] < datos["exactitud_anterior"]
    assert "no se activó" in datos["mensaje"]
    assert admin.get("/clasificador/estado").json()["version"] == "nb-v2"

    async def modelos(session):
        filas = await session.scalars(select(ClassifierModel).order_by(ClassifierModel.version))
        return [(m.version, m.is_active) for m in filas]

    assert entorno.correr(modelos) == [("nb-v2", True), ("nb-v3", False)]

    # Cada reentrenamiento queda en la auditoría, activado o no.
    registros = _auditoria(entorno, ACCION_REENTRENADO)
    assert [(r.new_values["version"], r.new_values["activado"]) for r in registros] == [
        ("nb-v2", True),
        ("nb-v3", False),
    ]
    assert all(r.actor_id == entorno.ids["admin"] for r in registros)


def test_reentrenar_compara_contra_la_exactitud_del_modelo_base(entorno) -> None:
    datos = entorno.como("administrator").post("/clasificador/reentrenar").json()
    assert datos["version_anterior"] == "nb-v1"
    assert datos["exactitud_anterior"] is not None
    assert datos["activado"] is (datos["exactitud"] >= round(datos["exactitud_anterior"], 4))


# ------------------------------------------------------------------- modelo guardado


def test_los_parametros_serializados_predicen_igual_que_el_modelo_entrenado() -> None:
    ejemplos = cargar_ejemplos(ruta_dataset())
    original = ClasificadorBayes(ejemplos, medir_exactitud=False, version="nb-v7")
    copia = ClasificadorBayes.desde_parametros(
        json.loads(json.dumps(original.parametros())),
        version="nb-v7",
        exactitud=0.8,
        entrenado_en=datetime(2026, 11, 1, tzinfo=UTC),
    )
    for ejemplo in ejemplos[:20]:
        assert copia.predecir(ejemplo.texto) == original.predecir(ejemplo.texto)
    assert (copia.version, copia.exactitud) == ("nb-v7", 0.8)


def test_el_dataset_mas_reciente_es_el_de_mayor_numero(monkeypatch, tmp_path) -> None:
    datos = tmp_path / "ml" / "data"
    datos.mkdir(parents=True)
    for nombre in ("dataset_v1.csv", "dataset_v2.csv", "dataset_v10.csv", "dataset_vx.csv"):
        (datos / nombre).write_text("", encoding="utf-8")
    monkeypatch.setattr(clasificador_client, "RAIZ_REPO", tmp_path)
    assert ruta_dataset_mas_reciente().name == "dataset_v10.csv"


def test_sin_datasets_numerados_usa_el_configurado(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(clasificador_client, "RAIZ_REPO", tmp_path)
    assert ruta_dataset_mas_reciente() == ruta_dataset()


# ------------------------------------------------------------------------- permisos

RUTAS = [
    ("get", "/clasificador/estado", None),
    ("put", "/clasificador/umbral", {"umbral": 0.7}),
    ("post", "/clasificador/reentrenar", None),
]


def test_solo_administrator_tiene_el_permiso_de_administrar_el_clasificador() -> None:
    con_permiso = {r for r in RoleName if has_permission(r, Permission.CLASSIFICATION_MANAGE)}
    assert con_permiso == {RoleName.ADMINISTRATOR}


@pytest.mark.parametrize("rol", [r.value for r in RoleName if r != RoleName.ADMINISTRATOR])
@pytest.mark.parametrize(("metodo", "ruta", "cuerpo"), RUTAS)
def test_los_demas_roles_reciben_403(entorno, rol, metodo, ruta, cuerpo) -> None:
    cliente = entorno.como(rol)
    kwargs = {"json": cuerpo} if cuerpo is not None else {}
    assert getattr(cliente, metodo)(ruta, **kwargs).status_code == 403


@pytest.mark.parametrize(("metodo", "ruta", "cuerpo"), RUTAS)
def test_sin_sesion_responde_401(entorno, metodo, ruta, cuerpo) -> None:
    kwargs = {"json": cuerpo} if cuerpo is not None else {}
    assert getattr(entorno.client, metodo)(ruta, **kwargs).status_code == 401


# ------------------------------------------------------------------------ migración


def test_alembic_tiene_una_sola_cabeza_con_las_tablas_nuevas() -> None:
    scripts = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    cabezas = scripts.get_heads()
    assert len(cabezas) == 1
    migracion = scripts.get_revision(cabezas[0])
    texto = Path(migracion.path).read_text(encoding="utf-8")
    assert '"app_settings"' in texto and '"classifier_models"' in texto
