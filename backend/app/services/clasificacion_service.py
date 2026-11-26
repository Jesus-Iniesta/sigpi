"""Clasificación automática de solicitudes (S4-12, HU-02.1).

Propone categoría, urgencia e impacto para una solicitud y guarda el resultado con su
confianza y la versión del modelo que lo produjo (AC2). No cambia el estatus de la
solicitud: decidir si queda «Clasificada» o pasa a revisión es S4-13 y S4-14.

Desde S5-06 usa el modelo vigente de `classifier_models` (si el administrador reentrenó
uno) y expone el umbral vigente de `app_settings`; si no hay fila, el de `Settings`. Las
solicitudes ya clasificadas no se recalculan.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger, log_event
from app.integrations.clasificador_client import (
    Clasificador,
    ClasificadorBayes,
    Prediccion,
    obtener_clasificador,
)
from app.models.classification import ClassificationResult, ClassifierModel, ModelVersion
from app.models.request import Request
from app.repositories.clasificacion_repository import ClasificacionRepository
from app.repositories.clasificador_admin_repository import ClasificadorAdminRepository

logger = get_logger("clasificacion")

_DECIMALES = 4  # `Numeric(5, 4)` en `confidence` y `accuracy`

CLAVE_UMBRAL = "classification_confidence_threshold"

# Modelos reentrenados ya deserializados, por id: se arman una vez por proceso.
_MODELOS_CARGADOS: dict[uuid.UUID, ClasificadorBayes] = {}


def texto_de(request: Request) -> str:
    """Texto que se clasifica: título y descripción de la solicitud."""
    return f"{request.title}. {request.description}"


def _acotar(valor: float) -> float:
    return round(min(1.0, max(0.0, valor)), _DECIMALES)


def clasificador_de(modelo: ClassifierModel) -> ClasificadorBayes:
    """Clasificador listo para predecir a partir de una fila de `classifier_models`."""
    cargado = _MODELOS_CARGADOS.get(modelo.id)
    if cargado is None:
        cargado = ClasificadorBayes.desde_parametros(
            modelo.parameters,
            version=modelo.version,
            exactitud=float(modelo.accuracy),
            entrenado_en=modelo.created_at,
            artefacto=f"classifier_models/{modelo.version}",
        )
        _MODELOS_CARGADOS[modelo.id] = cargado
    return cargado


class ClasificacionService:
    def __init__(self, session: AsyncSession, clasificador: Clasificador | None = None) -> None:
        self._repository = ClasificacionRepository(session)
        self._admin = ClasificadorAdminRepository(session)
        # Un clasificador inyectado (pruebas) tiene prioridad sobre el modelo vigente.
        self._inyectado = clasificador
        self._clasificador: Clasificador = clasificador or obtener_clasificador()

    async def umbral_vigente(self) -> float:
        """Umbral de confianza (RN-06) de `app_settings`; si no hay fila, el de `Settings`."""
        ajuste = await self._admin.get_ajuste(CLAVE_UMBRAL)
        if ajuste is None:
            return settings.classification_confidence_threshold
        return float(ajuste.value)

    async def clasificador_vigente(self) -> Clasificador:
        """El reentrenado activo en `classifier_models` o, si no hay, el base (`nb-v1`)."""
        if self._inyectado is not None:
            return self._inyectado
        modelo = await self._admin.modelo_activo()
        return clasificador_de(modelo) if modelo is not None else obtener_clasificador()

    async def clasificar(self, request: Request, *, confirmar: bool = True) -> ClassificationResult:
        """Clasifica la solicitud, guarda el resultado y confirma la transacción.

        Con `confirmar=False` el resultado queda en la transacción en curso para que quien
        orquesta lo confirme junto con el estatus de la solicitud (regla 7).
        """
        self._clasificador = await self.clasificador_vigente()
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
        if confirmar:
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
