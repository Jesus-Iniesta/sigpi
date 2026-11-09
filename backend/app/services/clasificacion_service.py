"""Clasificación automática de solicitudes (S4-12, HU-02.1).

Propone categoría, urgencia e impacto para una solicitud y guarda el resultado con su
confianza y la versión del modelo que lo produjo (AC2). No cambia el estatus de la
solicitud: decidir si queda «Clasificada» o pasa a revisión es S4-13 y S4-14.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, log_event
from app.integrations.clasificador_client import Clasificador, Prediccion, obtener_clasificador
from app.models.classification import ClassificationResult, ModelVersion
from app.models.request import Request
from app.repositories.clasificacion_repository import ClasificacionRepository

logger = get_logger("clasificacion")

_DECIMALES = 4  # `Numeric(5, 4)` en `confidence` y `accuracy`


def texto_de(request: Request) -> str:
    """Texto que se clasifica: título y descripción de la solicitud."""
    return f"{request.title}. {request.description}"


def _acotar(valor: float) -> float:
    return round(min(1.0, max(0.0, valor)), _DECIMALES)


class ClasificacionService:
    def __init__(self, session: AsyncSession, clasificador: Clasificador | None = None) -> None:
        self._repository = ClasificacionRepository(session)
        self._clasificador = clasificador if clasificador is not None else obtener_clasificador()

    async def clasificar(self, request: Request) -> ClassificationResult:
        """Clasifica la solicitud, guarda el resultado y confirma la transacción."""
        prediccion = self._clasificador.predecir(texto_de(request))
        model_version = await self._version_para(prediccion)
        result = await self._repository.add_result(
            ClassificationResult(
                request_id=request.id,
                model_version_id=model_version.id,
                category_id=await self._repository.find_category_id(prediccion.categoria),
                source=prediccion.fuente,
                confidence=_acotar(prediccion.confianza),
                urgency=prediccion.urgencia,
                impact=prediccion.impacto,
            )
        )
        await self._repository.commit()
        log_event(
            logger,
            "solicitud_clasificada",
            folio=request.folio,
            categoria=prediccion.categoria,
            fuente=str(prediccion.fuente),
            version=prediccion.version,
            confianza=float(result.confidence),
        )
        return result

    async def _version_para(self, prediccion: Prediccion) -> ModelVersion:
        """Reutiliza la `ModelVersion` de la predicción o la registra la primera vez."""
        existente = await self._repository.get_model_version(prediccion.version)
        if existente is not None:
            return existente
        # Si el modelo falló y la predicción vino de reglas, no hereda su exactitud.
        propia = prediccion.version == self._clasificador.version
        exactitud = self._clasificador.exactitud if propia else None
        return await self._repository.add_model_version(
            ModelVersion(
                version=prediccion.version,
                artifact_uri=self._clasificador.artefacto if propia else None,
                accuracy=None if exactitud is None else _acotar(exactitud),
                trained_at=self._clasificador.entrenado_en if propia else datetime.now(UTC),
                is_active=True,
            )
        )
