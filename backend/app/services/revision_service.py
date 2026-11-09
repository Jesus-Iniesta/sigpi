"""Umbral de confianza y cola de revisión de clasificaciones (S4-14, HU-02.2 AC1).

Una clasificación con confianza menor que el umbral (RN-06) deja la solicitud «Por
revisar» (`pending_review`); si alcanza el umbral queda «Clasificada». El umbral se lee
de `settings.classification_confidence_threshold`; que el administrador lo cambie desde
la interfaz queda fuera del Sprint 4.
"""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.clasificacion import requiere_revision
from app.models.enums import RequestStatus
from app.repositories.revision_repository import RevisionRepository
from app.schemas.revision import RevisionItem


class _ConConfianza(Protocol):
    confidence: float


def decidir_estatus(resultado: _ConConfianza, umbral: float | None = None) -> RequestStatus:
    """Estatus que corresponde a una solicitud según la confianza de su clasificación."""
    limite = settings.classification_confidence_threshold if umbral is None else umbral
    if requiere_revision(resultado.confidence, limite):
        return RequestStatus.PENDING_REVIEW
    return RequestStatus.CLASSIFIED


class RevisionService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = RevisionRepository(session)

    async def cola(self) -> list[RevisionItem]:
        """Solicitudes «Por revisar» con su último resultado, de la más antigua a la más
        reciente. Una solicitud sin ningún resultado de clasificación no se incluye."""
        solicitudes = await self._repository.solicitudes_por_revisar()
        resultados = await self._repository.ultimos_resultados([s.id for s in solicitudes])
        return [
            RevisionItem.from_models(solicitud, resultados[solicitud.id])
            for solicitud in solicitudes
            if solicitud.id in resultados
        ]
