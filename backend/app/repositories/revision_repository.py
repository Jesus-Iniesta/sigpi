"""Consultas de la cola de revisión de clasificaciones (S4-14, HU-02.2).

Solo lee: no confirma transacciones. Las reglas viven en `services/revision_service.py`.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.classification import ClassificationResult
from app.models.enums import RequestStatus
from app.models.request import Request


class RevisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def solicitudes_por_revisar(self) -> list[Request]:
        """Solicitudes «Por revisar», de la más antigua a la más reciente."""
        result = await self._session.scalars(
            select(Request)
            .where(Request.status == RequestStatus.PENDING_REVIEW)
            .order_by(Request.created_at, Request.id)
        )
        return list(result)

    async def ultimos_resultados(
        self, request_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ClassificationResult]:
        """Último `ClassificationResult` de cada solicitud, con categoría y versión del modelo."""
        if not request_ids:
            return {}
        result = await self._session.scalars(
            select(ClassificationResult)
            .where(ClassificationResult.request_id.in_(request_ids))
            .options(
                selectinload(ClassificationResult.category),
                selectinload(ClassificationResult.model_version),
            )
            .order_by(ClassificationResult.created_at.desc(), ClassificationResult.id.desc())
        )
        ultimos: dict[uuid.UUID, ClassificationResult] = {}
        for resultado in result:
            ultimos.setdefault(resultado.request_id, resultado)
        return ultimos
