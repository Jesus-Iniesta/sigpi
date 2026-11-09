"""Contratos de la API de revisión de clasificaciones (S4-14).

`RevisionItem` debe coincidir campo por campo con el tipo del mismo nombre en
`frontend/src/api/revision.ts` (lo verifica `tests/api/test_revision_cola.py`).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.classification import ClassificationResult
from app.models.enums import ClassificationSource, Priority
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
