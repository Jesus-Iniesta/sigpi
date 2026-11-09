"""Pruebas del repositorio de correcciones de clasificación (S4-16, HU-02.2).

Verifican que cada corrección se guarde como ejemplo de reentrenamiento:
- `add` no confirma la transacción (la confirma el servicio de revisión, S4-14).
- Los valores corregidos mandan; los que la persona no cambió conservan los de la predicción.
- Si una clasificación se corrigió varias veces, solo cuenta la última.
- Las filas generadas tienen las mismas columnas que `ml/data/dataset_v1.csv`.

Usan SQLite en memoria, igual que las demás pruebas de repositorios y servicios.
"""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.db.base import Base
from app.models.catalog import Categoria
from app.models.classification import ClassificationCorrection, ClassificationResult
from app.models.enums import ClassificationSource, RequestChannel, RequestStatus, UserType
from app.models.identity import User
from app.models.request import Request
from app.repositories.correccion_repository import (
    FUENTE_CORRECCION,
    CorreccionRepository,
    EjemploReentrenamiento,
)

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

from ml.etl.build_dataset import COLUMNAS  # noqa: E402

INICIO = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def entorno():
    """Sesión con una revisora y dos categorías; cada prueba crea sus solicitudes."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with maker() as session:
        revisora = User(
            institutional_id="rev-001",
            full_name="Rita Revisora",
            email="revisora@example.test",
            user_type=UserType.TECHNICAL,
        )
        redes = Categoria(area_id=uuid.uuid4(), name="Redes")
        cuentas = Categoria(area_id=uuid.uuid4(), name="Cuentas y accesos")
        session.add_all([revisora, redes, cuentas])
        await session.commit()
        yield session, CorreccionRepository(session), revisora, redes, cuentas
    await engine.dispose()


async def _resultado(
    session: AsyncSession,
    *,
    folio: str,
    categoria: Categoria | None,
    urgencia: int = 2,
    impacto: int = 2,
    titulo: str = "No puedo entrar a mi correo",
    descripcion: str = "Dice que mi contraseña es incorrecta aunque no la cambié.",
) -> ClassificationResult:
    """Crea una solicitud y su clasificación de baja confianza."""
    solicitud = Request(
        folio=folio,
        title=titulo,
        description=descripcion,
        physical_location="Edificio B",
        channel=RequestChannel.PORTAL,
        status=RequestStatus.PENDING_REVIEW,
        created_at=INICIO,
    )
    session.add(solicitud)
    await session.flush()
    resultado = ClassificationResult(
        request_id=solicitud.id,
        category_id=categoria.id if categoria else None,
        source=ClassificationSource.MODEL,
        confidence=0.62,
        urgency=urgencia,
        impact=impacto,
        created_at=INICIO,
    )
    session.add(resultado)
    await session.commit()
    return resultado


def _correccion(
    resultado: ClassificationResult,
    revisora: User,
    *,
    cuando: datetime,
    categoria: Categoria | None = None,
    urgencia: int | None = None,
    impacto: int | None = None,
    justificacion: str = "El texto describe un problema de acceso, no de red.",
) -> ClassificationCorrection:
    return ClassificationCorrection(
        result_id=resultado.id,
        corrected_by_id=revisora.id,
        corrected_category_id=categoria.id if categoria else None,
        corrected_urgency=urgencia,
        corrected_impact=impacto,
        justification=justificacion,
        created_at=cuando,
    )


# --- add ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_guarda_la_correccion_con_sus_valores(entorno) -> None:
    session, repo, revisora, redes, cuentas = entorno
    resultado = await _resultado(session, folio="SIG-0001", categoria=redes)

    guardada = await repo.add(
        _correccion(resultado, revisora, cuando=INICIO, categoria=cuentas, urgencia=3, impacto=1)
    )
    await session.commit()

    assert guardada.id is not None
    leida = await session.get(ClassificationCorrection, guardada.id)
    assert leida is not None
    assert leida.corrected_category_id == cuentas.id
    assert (leida.corrected_urgency, leida.corrected_impact) == (3, 1)
    assert leida.justification.startswith("El texto describe")


@pytest.mark.asyncio
async def test_add_no_confirma_la_transaccion(entorno) -> None:
    """Si el servicio falla después de `add`, no debe quedar una corrección huérfana."""
    session, repo, revisora, redes, _cuentas = entorno
    resultado = await _resultado(session, folio="SIG-0001", categoria=redes)

    await repo.add(_correccion(resultado, revisora, cuando=INICIO, urgencia=3))
    await session.rollback()

    total = await session.scalar(select(func.count()).select_from(ClassificationCorrection))
    assert total == 0


# --- consultas por resultado ------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_by_result_va_de_la_mas_antigua_a_la_mas_reciente(entorno) -> None:
    session, repo, revisora, redes, cuentas = entorno
    resultado = await _resultado(session, folio="SIG-0001", categoria=redes)
    segunda = await repo.add(
        _correccion(resultado, revisora, cuando=INICIO + timedelta(hours=2), urgencia=3)
    )
    primera = await repo.add(
        _correccion(resultado, revisora, cuando=INICIO + timedelta(hours=1), categoria=cuentas)
    )
    await session.commit()

    correcciones = await repo.list_by_result(resultado.id)

    assert [c.id for c in correcciones] == [primera.id, segunda.id]


@pytest.mark.asyncio
async def test_get_latest_for_result_devuelve_la_ultima(entorno) -> None:
    session, repo, revisora, redes, _cuentas = entorno
    resultado = await _resultado(session, folio="SIG-0001", categoria=redes)
    await repo.add(_correccion(resultado, revisora, cuando=INICIO + timedelta(hours=1)))
    ultima = await repo.add(
        _correccion(resultado, revisora, cuando=INICIO + timedelta(hours=2), impacto=3)
    )
    await session.commit()

    vigente = await repo.get_latest_for_result(resultado.id)

    assert vigente is not None
    assert vigente.id == ultima.id


@pytest.mark.asyncio
async def test_get_latest_for_result_sin_correcciones_devuelve_none(entorno) -> None:
    session, repo, _revisora, redes, _cuentas = entorno
    resultado = await _resultado(session, folio="SIG-0001", categoria=redes)

    assert await repo.get_latest_for_result(resultado.id) is None
    assert await repo.list_by_result(resultado.id) == []


# --- ejemplos de reentrenamiento ----------------------------------------------------------


@pytest.mark.asyncio
async def test_sin_correcciones_no_hay_ejemplos(entorno) -> None:
    _session, repo, *_ = entorno

    assert await repo.list_training_examples() == []


@pytest.mark.asyncio
async def test_el_ejemplo_usa_los_valores_corregidos(entorno) -> None:
    session, repo, revisora, redes, cuentas = entorno
    resultado = await _resultado(session, folio="SIG-0007", categoria=redes, urgencia=2, impacto=2)
    await repo.add(
        _correccion(resultado, revisora, cuando=INICIO, categoria=cuentas, urgencia=3, impacto=1)
    )
    await session.commit()

    [ejemplo] = await repo.list_training_examples()

    assert isinstance(ejemplo, EjemploReentrenamiento)
    assert ejemplo.folio == "SIG-0007"
    assert ejemplo.category_id == cuentas.id
    assert ejemplo.category_name == "Cuentas y accesos"
    assert (ejemplo.urgency, ejemplo.impact) == (3, 1)
    assert ejemplo.result_id == resultado.id
    assert ejemplo.request_id == resultado.request_id


@pytest.mark.asyncio
async def test_lo_que_no_se_corrige_conserva_el_valor_de_la_prediccion(entorno) -> None:
    session, repo, revisora, redes, _cuentas = entorno
    resultado = await _resultado(session, folio="SIG-0001", categoria=redes, urgencia=2, impacto=3)
    # Solo cambia la urgencia: categoría e impacto se quedan como los propuso el modelo.
    await repo.add(_correccion(resultado, revisora, cuando=INICIO, urgencia=1))
    await session.commit()

    [ejemplo] = await repo.list_training_examples()

    assert ejemplo.category_name == "Redes"
    assert (ejemplo.urgency, ejemplo.impact) == (1, 3)


@pytest.mark.asyncio
async def test_solo_cuenta_la_ultima_correccion_de_cada_resultado(entorno) -> None:
    session, repo, revisora, redes, cuentas = entorno
    resultado = await _resultado(session, folio="SIG-0001", categoria=redes)
    await repo.add(
        _correccion(resultado, revisora, cuando=INICIO + timedelta(hours=1), categoria=cuentas)
    )
    await repo.add(
        _correccion(resultado, revisora, cuando=INICIO + timedelta(hours=2), categoria=redes)
    )
    await session.commit()

    ejemplos = await repo.list_training_examples()

    assert len(ejemplos) == 1
    assert ejemplos[0].category_name == "Redes"


@pytest.mark.asyncio
async def test_los_ejemplos_van_de_la_correccion_mas_antigua_a_la_mas_reciente(entorno) -> None:
    session, repo, revisora, redes, _cuentas = entorno
    reciente = await _resultado(session, folio="SIG-0002", categoria=redes)
    antigua = await _resultado(session, folio="SIG-0001", categoria=redes)
    await repo.add(_correccion(reciente, revisora, cuando=INICIO + timedelta(hours=5)))
    await repo.add(_correccion(antigua, revisora, cuando=INICIO + timedelta(hours=1)))
    await session.commit()

    ejemplos = await repo.list_training_examples()

    assert [e.folio for e in ejemplos] == ["SIG-0001", "SIG-0002"]


@pytest.mark.asyncio
async def test_sin_categoria_en_ningun_lado_el_ejemplo_se_omite(entorno) -> None:
    session, repo, revisora, redes, _cuentas = entorno
    sin_etiqueta = await _resultado(session, folio="SIG-0001", categoria=None)
    con_etiqueta = await _resultado(session, folio="SIG-0002", categoria=redes)
    await repo.add(_correccion(sin_etiqueta, revisora, cuando=INICIO, urgencia=2))
    await repo.add(_correccion(con_etiqueta, revisora, cuando=INICIO, urgencia=2))
    await session.commit()

    ejemplos = await repo.list_training_examples()

    assert [e.folio for e in ejemplos] == ["SIG-0002"]


@pytest.mark.asyncio
async def test_since_deja_solo_las_correcciones_desde_esa_fecha(entorno) -> None:
    session, repo, revisora, redes, _cuentas = entorno
    vieja = await _resultado(session, folio="SIG-0001", categoria=redes)
    nueva = await _resultado(session, folio="SIG-0002", categoria=redes)
    await repo.add(_correccion(vieja, revisora, cuando=INICIO))
    await repo.add(_correccion(nueva, revisora, cuando=INICIO + timedelta(days=2)))
    await session.commit()

    ejemplos = await repo.list_training_examples(since=INICIO + timedelta(days=1))

    assert [e.folio for e in ejemplos] == ["SIG-0002"]


# --- formato del ejemplo ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_el_texto_une_titulo_y_descripcion(entorno) -> None:
    session, repo, revisora, redes, _cuentas = entorno
    resultado = await _resultado(
        session,
        folio="SIG-0001",
        categoria=redes,
        titulo="Sin internet en el laboratorio.",
        descripcion="  Desde las 9:00 no hay red en las 20 computadoras.  ",
    )
    await repo.add(_correccion(resultado, revisora, cuando=INICIO))
    await session.commit()

    [ejemplo] = await repo.list_training_examples()

    assert ejemplo.text == (
        "Sin internet en el laboratorio. Desde las 9:00 no hay red en las 20 computadoras."
    )


@pytest.mark.asyncio
async def test_la_fila_tiene_las_columnas_del_conjunto_de_datos(entorno) -> None:
    session, repo, revisora, redes, cuentas = entorno
    resultado = await _resultado(session, folio="SIG-0001", categoria=redes)
    await repo.add(
        _correccion(resultado, revisora, cuando=INICIO, categoria=cuentas, urgencia=3, impacto=2)
    )
    await session.commit()

    [ejemplo] = await repo.list_training_examples()
    fila = ejemplo.to_dataset_row()

    assert tuple(fila) == COLUMNAS
    assert fila["category"] == "Cuentas y accesos"
    assert (fila["urgency"], fila["impact"]) == (3, 2)
    assert fila["source"] == FUENTE_CORRECCION
    assert str(fila["id"]).startswith("COR-")
