"""Contratos de la API de revisión de clasificaciones (S4-14 y S4-16).

`RevisionItem`, `RevisionInput` y `RevisionResult` deben coincidir campo por campo con
los tipos del mismo nombre en `frontend/src/api/revision.ts` (lo verifican
`tests/api/test_revision_cola.py` y `tests/api/test_correccion.py`).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.models.classification import ClassificationResult
from app.models.enums import ClassificationSource, Priority, RequestStatus
from app.models.request import Request


class RevisionItem(BaseModel):
    """Una clasificación de baja confianza que espera revisión humana."""

    result_id: uuid.UUID
    request_id: uuid.UUID
    folio: str
    title: str
    description: str
    created_at: datetime
    category_id: uuid.UUID | None
    category_name: str | None
    urgency: int
    impact: int
    priority: Priority | None
    confidence: float = Field(ge=0, le=1)
    source: ClassificationSource
    model_version: str | None

    @classmethod
    def from_models(cls, request: Request, resultado: ClassificationResult) -> "RevisionItem":
        return cls(
            result_id=resultado.id,
            request_id=request.id,
            folio=request.folio,
            title=request.title,
            description=request.description,
            created_at=request.created_at,
            category_id=resultado.category_id,
            category_name=resultado.category.name if resultado.category is not None else None,
            urgency=resultado.urgency,
            impact=resultado.impact,
            priority=Priority(request.priority) if request.priority else None,
            confidence=float(resultado.confidence),
            source=ClassificationSource(resultado.source),
            model_version=(
                resultado.model_version.version if resultado.model_version is not None else None
            ),
        )


JUSTIFICACION_MINIMA = 10


class RevisionInput(BaseModel):
    """Lo que decide la persona revisora (S4-16). La prioridad no se captura: la recalcula
    el servidor con la urgencia y el impacto (RN-05).

    Debe coincidir con `RevisionInput` de `frontend/src/api/revision.ts`.
    """

    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID
    urgency: int = Field(ge=1, le=3)
    impact: int = Field(ge=1, le=3)
    # `None` por omisión con `validate_default` para que la falta del campo también
    # responda con un mensaje en español (COR-07) y no con el «Field required» de Pydantic.
    justification: str | None = Field(default=None, validate_default=True)

    @field_validator("justification")
    @classmethod
    def _justificacion_obligatoria(cls, value: str | None) -> str:
        texto = (value or "").strip()
        if not texto:
            raise PydanticCustomError("missing", "La justificación es obligatoria.")
        if len(texto) < JUSTIFICACION_MINIMA:
            raise PydanticCustomError(
                "string_too_short",
                "La justificación debe tener al menos {min_length} caracteres.",
                {"min_length": JUSTIFICACION_MINIMA},
            )
        return texto


class RevisionResult(BaseModel):
    """Estado de la solicitud después de guardar la corrección."""

    request_id: uuid.UUID
    status: RequestStatus
    priority: Priority | None
