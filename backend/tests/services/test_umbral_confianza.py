"""Pruebas del umbral de confianza y de la cola de revisión (S4-14, HU-02.2, RN-06).

`tests/api/test_revision_cola.py` prueba la regla, el endpoint y el orden de la cola. Aquí
van dos casos que esa prueba no cubre:

- El umbral configurado debe estar entre 0 y 1: un valor fuera de rango se rechaza al
  arrancar, en lugar de mandar todas las solicitudes a revisión (o ninguna) sin avisar.
- Una solicitud «Por revisar» sin resultado de clasificación no aparece en la cola.
"""

import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra todas las tablas en Base.metadata)
from app.core.config import Settings
from app.db.base import Base
from app.models.classification import ClassificationResult
from app.models.enums import ClassificationSource, RequestChannel, RequestStatus
from app.models.request import Request
from app.services.revision_service import RevisionService

VARIABLE = "CLASSIFICATION_CONFIDENCE_THRESHOLD"


def _ajustes(**valores) -> Settings:
    """`Settings` sin leer el `.env` local, para que la prueba no dependa de la máquina."""
    return Settings(_env_file=None, **valores)


# --- Límites del umbral --------------------------------------------------------------


def test_el_umbral_por_defecto_es_0_75(monkeypatch) -> None:
    monkeypatch.delenv(VARIABLE, raising=False)

    assert _ajustes().classification_confidence_threshold == 0.75


@pytest.mark.parametrize("valor", [0, 0.5, 0.75, 1])
def test_acepta_umbrales_de_0_a_1(valor) -> None:
    ajustes = _ajustes(classification_confidence_threshold=valor)

    assert ajustes.classification_confidence_threshold == valor


@pytest.mark.parametrize("valor", [-0.01, 1.01, 75])
def test_rechaza_umbrales_fuera_de_0_a_1(valor) -> None:
    with pytest.raises(ValidationError, match="classification_confidence_threshold"):
        _ajustes(classification_confidence_threshold=valor)


def test_el_umbral_se_lee_de_la_variable_de_entorno(monkeypatch) -> None:
    monkeypatch.setenv(VARIABLE, "0.9")

    assert _ajustes().classification_confidence_threshold == 0.9


def test_una_variable_de_entorno_fuera_de_rango_se_rechaza_al_arrancar(monkeypatch) -> None:
    monkeypatch.setenv(VARIABLE, "75")

    with pytest.raises(ValidationError, match="classification_confidence_threshold"):
        _ajustes()


# --- Cola de revisión ----------------------------------------------------------------


def _por_revisar(folio: str) -> Request:
    return Request(
        folio=folio,
        title=f"Solicitud {folio}",
        description="No hay red en el laboratorio.",
        physical_location="Edificio B",
        channel=RequestChannel.PORTAL,
        status=RequestStatus.PENDING_REVIEW,
    )


def test_la_cola_omite_la_solicitud_por_revisar_que_no_tiene_resultado() -> None:
    async def probar() -> list[str]:
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            con_resultado = _por_revisar("SIG-0001")
            sin_resultado = _por_revisar("SIG-0002")
            session.add_all([con_resultado, sin_resultado])
            await session.flush()
            session.add(
                ClassificationResult(
                    request_id=con_resultado.id,
                    source=ClassificationSource.RULES,
                    confidence=0.6,
                    urgency=2,
                    impact=2,
                )
            )
            await session.commit()
            cola = await RevisionService(session).cola()
        await engine.dispose()
        return [item.folio for item in cola]

    assert asyncio.run(probar()) == ["SIG-0001"]
