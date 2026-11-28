"""Pruebas del servicio de administración del clasificador (S5-24, HU-02.2, HU-12.1).

Complementan `tests/api/test_clasificador_admin.py` desde la capa de servicio:

- estado sin modelo reentrenado, incluso si el conjunto de datos base no se puede leer;
- umbral fuera de rango (`UmbralFueraDeRangoError`) y los límites aceptados;
- reentrenamientos sucesivos que dejan una versión nueva y su auditoría.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.core.config import settings
from app.db.base import Base
from app.domain.auditoria import AuditContext
from app.models.app_setting import AppSetting
from app.models.auditoria import Auditoria
from app.models.classification import ClassifierModel
from app.models.enums import UserType
from app.models.identity import User
from app.schemas.clasificador import UMBRAL_MAXIMO, UMBRAL_MINIMO
from app.services import clasificador_admin_service
from app.services.clasificador_admin_service import (
    ACCION_REENTRENADO,
    ACCION_UMBRAL,
    ClasificadorAdminService,
    UmbralFueraDeRangoError,
)

AHORA = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)


@pytest.fixture
def entorno(monkeypatch):
    # El modelo base no se midió: así cualquier reentrenamiento queda vigente.
    monkeypatch.setattr(
        clasificador_admin_service,
        "obtener_clasificador",
        lambda: SimpleNamespace(version="nb-v1", exactitud=None),
    )
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    admin_id = uuid.uuid4()

    async def preparar() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            session.add(
                User(
                    id=admin_id,
                    institutional_id="adm-001",
                    full_name="Administración",
                    email="adm-001@example.test",
                    user_type=UserType.ADMINISTRATIVE,
                    is_active=True,
                )
            )
            await session.commit()

    def correr(fn):
        async def envolver():
            async with maker() as session:
                return await fn(session)

        return asyncio.run(envolver())

    asyncio.run(preparar())
    try:
        yield SimpleNamespace(correr=correr, contexto=AuditContext(actor_id=admin_id))
    finally:
        asyncio.run(engine.dispose())


def _filas(e, modelo) -> list:
    async def leer(session):
        return list(await session.scalars(select(modelo)))

    return e.correr(leer)


# --- estado ------------------------------------------------------------------------


def _csv_sin_columnas(tmp_path: Path) -> Path:
    ruta = tmp_path / "sin_columnas.csv"
    ruta.write_text("otra,columna\n1,2\n", encoding="utf-8")
    return ruta


def _csv_vacio(tmp_path: Path) -> Path:
    ruta = tmp_path / "vacio.csv"
    ruta.write_text("id,text,category,urgency,impact,source\n", encoding="utf-8")
    return ruta


@pytest.mark.parametrize(
    "dataset",
    [
        pytest.param(lambda tmp: tmp / "no_existe.csv", id="archivo-inexistente"),
        pytest.param(_csv_sin_columnas, id="columnas-faltantes"),
        pytest.param(_csv_vacio, id="sin-ejemplos"),
    ],
)
def test_el_estado_sin_modelo_entrenado_tolera_un_dataset_ilegible(
    entorno, monkeypatch, tmp_path, dataset
) -> None:
    ruta = dataset(tmp_path)
    monkeypatch.setattr(clasificador_admin_service, "ruta_dataset", lambda: ruta)

    estado = entorno.correr(lambda s: ClasificadorAdminService(s).estado(ahora=AHORA))

    assert estado.version == "nb-v1"
    assert estado.ejemplos == 0
    assert estado.exactitud is None
    assert estado.entrenado_en is None
    assert estado.umbral == settings.classification_confidence_threshold
    assert estado.proporcion_por_revisar is None
    assert estado.correcciones_pendientes == 0


# --- umbral ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "umbral",
    [UMBRAL_MINIMO - 0.01, UMBRAL_MAXIMO + 0.01, 0.0, 1.0, -0.5],
)
def test_un_umbral_fuera_de_rango_no_se_guarda_ni_se_audita(entorno, umbral) -> None:
    with pytest.raises(UmbralFueraDeRangoError):
        entorno.correr(
            lambda s: ClasificadorAdminService(s).cambiar_umbral(umbral, entorno.contexto)
        )

    assert _filas(entorno, AppSetting) == []
    assert _filas(entorno, Auditoria) == []


@pytest.mark.parametrize("umbral", [UMBRAL_MINIMO, UMBRAL_MAXIMO])
def test_los_limites_del_rango_se_aceptan(entorno, umbral) -> None:
    resultado = entorno.correr(
        lambda s: ClasificadorAdminService(s).cambiar_umbral(umbral, entorno.contexto)
    )

    assert resultado.umbral == umbral
    assert resultado.umbral_anterior == settings.classification_confidence_threshold
    [registro] = _filas(entorno, Auditoria)
    assert registro.action == ACCION_UMBRAL
    assert registro.actor_id == entorno.contexto.actor_id
    assert registro.new_values == {"umbral": umbral}


# --- reentrenamiento ---------------------------------------------------------------


def test_cada_reentrenamiento_deja_una_version_nueva_y_su_auditoria(entorno) -> None:
    def reentrenar(session):
        return ClasificadorAdminService(session).reentrenar(entorno.contexto)

    primera = entorno.correr(reentrenar)
    segunda = entorno.correr(reentrenar)

    assert (primera.version, primera.version_anterior) == ("nb-v2", "nb-v1")
    assert (segunda.version, segunda.version_anterior) == ("nb-v3", "nb-v2")
    assert segunda.exactitud_anterior == primera.exactitud
    assert primera.activado and segunda.activado
    assert primera.correcciones_incorporadas == 0

    modelos = {m.version: m for m in _filas(entorno, ClassifierModel)}
    assert set(modelos) == {"nb-v2", "nb-v3"}
    assert [v for v, m in modelos.items() if m.is_active] == ["nb-v3"]

    auditoria = [a for a in _filas(entorno, Auditoria) if a.action == ACCION_REENTRENADO]
    assert sorted(a.new_values["version"] for a in auditoria) == ["nb-v2", "nb-v3"]
    assert {a.entity_id for a in auditoria} == {str(m.id) for m in modelos.values()}
    assert all(a.actor_id == entorno.contexto.actor_id for a in auditoria)

    estado = entorno.correr(lambda s: ClasificadorAdminService(s).estado(ahora=AHORA))
    assert estado.version == "nb-v3"
    assert estado.ejemplos == segunda.ejemplos
    assert estado.entrenado_en is not None
