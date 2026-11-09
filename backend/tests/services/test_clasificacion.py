"""Pruebas del servicio de clasificación de solicitudes (S4-12, HU-02.1)."""

import asyncio
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.integrations.clasificador_client import (
    CATEGORIAS,
    VERSION_BAYES,
    VERSION_REGLAS,
    ClasificadorBayes,
    ClasificadorCompuesto,
    ClasificadorReglas,
    Prediccion,
    cargar_ejemplos,
    impacto_por_reglas,
    particiones,
    ruta_dataset,
    tokenizar,
    urgencia_por_reglas,
    validacion_cruzada,
)
from app.models.catalog import AreaServicio, Categoria
from app.models.classification import ClassificationResult, ModelVersion
from app.models.enums import ClassificationSource, RequestChannel, RequestStatus
from app.models.request import Request
from app.services.clasificacion_service import ClasificacionService

# Una solicitud de ejemplo por categoría, redactada fuera del conjunto de datos.
EJEMPLOS_POR_CATEGORIA: dict[str, str] = {
    "Hardware": "La impresora de la oficina no enciende y el monitor parpadea.",
    "Software": "Necesito instalar la licencia de Office y actualizar el antivirus.",
    "Redes": "No hay internet en el edificio, el wifi no conecta y la red está caída.",
    "Cuentas y accesos": "Olvidé mi contraseña y la cuenta quedó bloqueada, no puedo iniciar sesión.",
}


@pytest.fixture(scope="module")
def bayes() -> ClasificadorBayes:
    return ClasificadorBayes.desde_csv(ruta_dataset())


@pytest.fixture
def db():
    """Base SQLite en memoria con las cuatro categorías del catálogo."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    categorias: dict[str, uuid.UUID] = {}

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            area = AreaServicio(unit_id=uuid.uuid4(), name="Soporte")
            session.add(area)
            await session.flush()
            for nombre in CATEGORIAS:
                categoria = Categoria(area_id=area.id, name=nombre)
                session.add(categoria)
                await session.flush()
                categorias[nombre] = categoria.id
            await session.commit()

    asyncio.run(prepare())
    try:
        yield maker, categorias
    finally:
        asyncio.run(engine.dispose())


def _crear_solicitud(maker, descripcion: str) -> Request:
    async def run() -> Request:
        async with maker() as session:
            request = Request(
                folio=f"SIG-{uuid.uuid4().hex[:6]}",
                title="Solicitud de soporte",
                description=descripcion,
                physical_location="Edificio A",
                channel=RequestChannel.PORTAL,
                status=RequestStatus.REGISTERED,
            )
            session.add(request)
            await session.commit()
            return request

    return asyncio.run(run())


def _clasificar(maker, request: Request, clasificador) -> ClassificationResult:
    async def run() -> ClassificationResult:
        async with maker() as session:
            return await ClasificacionService(session, clasificador).clasificar(request)

    return asyncio.run(run())


def _consultar(maker, modelo, *condiciones):
    async def run():
        async with maker() as session:
            return list(await session.scalars(select(modelo).where(*condiciones)))

    return asyncio.run(run())


# --- tokenización ------------------------------------------------------------


def test_tokenizar_quita_mayusculas_acentos_y_palabras_vacias():
    assert tokenizar("La CONTRASEÑA del Módulo no sirve") == ["contrasena", "modulo", "no", "sirve"]


# --- AC: una solicitud por categoría se clasifica bien -------------------------


@pytest.mark.parametrize(("categoria", "texto"), EJEMPLOS_POR_CATEGORIA.items())
def test_modelo_clasifica_un_ejemplo_por_categoria(bayes, categoria, texto):
    prediccion = bayes.predecir(texto)
    assert prediccion.categoria == categoria
    assert prediccion.fuente == ClassificationSource.MODEL
    assert prediccion.version == VERSION_BAYES


@pytest.mark.parametrize(("categoria", "texto"), EJEMPLOS_POR_CATEGORIA.items())
def test_reglas_clasifican_un_ejemplo_por_categoria(categoria, texto):
    prediccion = ClasificadorReglas().predecir(texto)
    assert prediccion.categoria == categoria
    assert prediccion.fuente == ClassificationSource.RULES
    assert prediccion.version == VERSION_REGLAS


@pytest.mark.parametrize(("categoria", "texto"), EJEMPLOS_POR_CATEGORIA.items())
def test_servicio_guarda_la_categoria_del_catalogo(db, categoria, texto):
    maker, categorias = db
    request = _crear_solicitud(maker, texto)

    result = _clasificar(maker, request, ClasificadorCompuesto(ruta_dataset()))

    assert result.category_id == categorias[categoria]
    assert result.source == ClassificationSource.MODEL


# --- AC: menos de cinco segundos ---------------------------------------------


def test_cincuenta_predicciones_tardan_menos_de_cinco_segundos(bayes):
    textos = [e.texto for e in cargar_ejemplos(ruta_dataset())][:50]
    assert len(textos) == 50

    inicio = time.perf_counter()
    predicciones = [bayes.predecir(t) for t in textos]
    duracion = time.perf_counter() - inicio

    assert len(predicciones) == 50
    assert duracion < 5


# --- AC: sin CSV cae a reglas ------------------------------------------------


def test_sin_csv_el_compuesto_usa_reglas(tmp_path: Path):
    clasificador = ClasificadorCompuesto(tmp_path / "no-existe.csv")

    prediccion = clasificador.predecir(EJEMPLOS_POR_CATEGORIA["Redes"])

    assert clasificador.version == VERSION_REGLAS
    assert prediccion.fuente == ClassificationSource.RULES
    assert prediccion.version == VERSION_REGLAS


def test_csv_invalido_tambien_cae_a_reglas(tmp_path: Path):
    ruta = tmp_path / "roto.csv"
    ruta.write_text("columna_equivocada\nvalor\n", encoding="utf-8")

    assert ClasificadorCompuesto(ruta).version == VERSION_REGLAS


def test_sin_csv_el_servicio_guarda_source_rules_y_reglas_v1(db, tmp_path: Path):
    maker, categorias = db
    request = _crear_solicitud(maker, EJEMPLOS_POR_CATEGORIA["Hardware"])

    result = _clasificar(maker, request, ClasificadorCompuesto(tmp_path / "no-existe.csv"))

    guardado = _consultar(maker, ClassificationResult, ClassificationResult.id == result.id)[0]
    version = _consultar(maker, ModelVersion, ModelVersion.id == guardado.model_version_id)[0]
    assert guardado.source == ClassificationSource.RULES
    assert version.version == VERSION_REGLAS
    assert version.accuracy is None
    assert guardado.category_id == categorias["Hardware"]


def test_si_el_modelo_falla_al_predecir_usa_reglas(monkeypatch):
    clasificador = ClasificadorCompuesto(ruta_dataset())

    def falla(_texto: str) -> Prediccion:
        raise RuntimeError("modelo dañado")

    monkeypatch.setattr(clasificador._modelo, "predecir", falla)

    assert clasificador.predecir("La impresora no enciende").fuente == ClassificationSource.RULES


# --- AC: confianza entre 0 y 1 y versión guardada ------------------------------


def test_resultado_guarda_confianza_y_version_y_confirma(db):
    maker, _ = db
    request = _crear_solicitud(maker, EJEMPLOS_POR_CATEGORIA["Software"])
    clasificador = ClasificadorCompuesto(ruta_dataset())

    result = _clasificar(maker, request, clasificador)

    # Se lee en otra sesión: solo aparece si el servicio hizo `commit`.
    guardados = _consultar(
        maker, ClassificationResult, ClassificationResult.request_id == request.id
    )
    assert [g.id for g in guardados] == [result.id]
    assert 0 <= float(guardados[0].confidence) <= 1
    version = _consultar(maker, ModelVersion, ModelVersion.id == guardados[0].model_version_id)[0]
    assert version.version == VERSION_BAYES
    assert version.artifact_uri == "ml/data/dataset_v1.csv"
    assert float(version.accuracy) == pytest.approx(clasificador.exactitud, abs=1e-4)
    assert guardados[0].urgency in (1, 2, 3)
    assert guardados[0].impact in (1, 2, 3)


def test_reutiliza_la_model_version_existente(db):
    maker, _ = db
    clasificador = ClasificadorCompuesto(ruta_dataset())

    primero = _clasificar(maker, _crear_solicitud(maker, "La red no funciona"), clasificador)
    segundo = _clasificar(maker, _crear_solicitud(maker, "El mouse no sirve"), clasificador)

    assert primero.model_version_id == segundo.model_version_id
    assert len(_consultar(maker, ModelVersion, ModelVersion.version == VERSION_BAYES)) == 1


def test_no_cambia_el_estatus_de_la_solicitud(db):
    maker, _ = db
    request = _crear_solicitud(maker, EJEMPLOS_POR_CATEGORIA["Redes"])

    _clasificar(maker, request, ClasificadorCompuesto(ruta_dataset()))

    guardada = _consultar(maker, Request, Request.id == request.id)[0]
    assert guardada.status == RequestStatus.REGISTERED
    assert guardada.category_id is None


def test_categoria_fuera_del_catalogo_se_guarda_sin_category_id(db):
    maker, _ = db

    class Fijo:
        version = "fijo-v1"
        fuente = ClassificationSource.RULES
        exactitud = None
        artefacto = None
        entrenado_en = ClasificadorReglas().entrenado_en

        def predecir(self, texto: str) -> Prediccion:
            return Prediccion("Telefonía", 2, 2, 1.5, self.fuente, self.version)

    result = _clasificar(maker, _crear_solicitud(maker, "El teléfono no da tono"), Fijo())

    assert result.category_id is None
    assert float(result.confidence) == 1.0  # se acota a [0, 1]


@pytest.mark.parametrize("texto", [*EJEMPLOS_POR_CATEGORIA.values(), "", "???"])
def test_confianza_siempre_entre_cero_y_uno(bayes, texto):
    for clasificador in (bayes, ClasificadorReglas()):
        assert 0 < clasificador.predecir(texto).confianza <= 1


# --- validación cruzada (RT-01) ---------------------------------------------


def test_particiones_estratificadas_cubren_todo_sin_repetir():
    ejemplos = cargar_ejemplos(ruta_dataset())
    partes = particiones(ejemplos, 5)

    indices = sorted(i for parte in partes for i in parte)
    assert indices == list(range(len(ejemplos)))
    for parte in partes:
        por_categoria = {c: sum(ejemplos[i].categoria == c for i in parte) for c in CATEGORIAS}
        assert set(por_categoria.values()) == {6}


def test_validacion_cruzada_es_determinista_y_supera_el_azar(bayes):
    ejemplos = cargar_ejemplos(ruta_dataset())

    resultado = validacion_cruzada(ejemplos, 5)

    assert resultado == validacion_cruzada(ejemplos, 5)
    assert resultado["categoria"] == bayes.exactitud
    # Cuatro categorías balanceadas: adivinar da 0.25.
    assert resultado["categoria"] > 0.25
    assert all(0 <= v <= 1 for v in resultado.values())


# --- señales de urgencia e impacto ------------------------------------------


@pytest.mark.parametrize(
    ("texto", "urgencia"),
    [
        ("El proyector no enciende y tengo examen hoy", 3),
        ("No es urgente, pero el teclado tiene una tecla floja", 1),
        ("El correo tarda en sincronizar", 2),
    ],
)
def test_urgencia_por_reglas(texto, urgencia):
    assert urgencia_por_reglas(texto) == urgencia


@pytest.mark.parametrize(
    ("texto", "impacto"),
    [
        ("Se cayó el internet de toda la facultad", 3),
        ("No funciona la red en todo el laboratorio", 2),
        ("Mi mouse no responde", 1),
    ],
)
def test_impacto_por_reglas(texto, impacto):
    assert impacto_por_reglas(texto) == impacto
