"""Acceso a datos de la clasificación de solicitudes (S4-12, HU-02.1).

Solo encapsula consultas y no confirma la transacción (COR-02): lo hace
`services/clasificacion_service.py`.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Categoria
from app.models.classification import ClassificationResult, ModelVersion


class ClasificacionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_category_id(self, nombre: str) -> uuid.UUID | None:
        """Id de la categoría con ese nombre, sin distinguir mayúsculas."""
        return await self._session.scalar(
            select(Categoria.id).where(func.lower(Categoria.name) == nombre.strip().lower())
        )

    async def get_model_version(self, version: str) -> ModelVersion | None:
        return await self._session.scalar(
            select(ModelVersion).where(ModelVersion.version == version)
        )

    async def add_model_version(self, model_version: ModelVersion) -> ModelVersion:
        self._session.add(model_version)
        await self._session.flush()
        return model_version

    async def add_result(self, result: ClassificationResult) -> ClassificationResult:
        self._session.add(result)
        await self._session.flush()
        return result

    async def list_for_request(self, request_id: uuid.UUID) -> list[ClassificationResult]:
        """Resultados de una solicitud, del más antiguo al más reciente."""
        result = await self._session.scalars(
            select(ClassificationResult)
            .where(ClassificationResult.request_id == request_id)
            .order_by(ClassificationResult.created_at, ClassificationResult.id)
        )
        return list(result)

    async def commit(self) -> None:
        """Confirma la transacción; la llama el servicio que orquesta el caso de uso."""
        await self._session.commit()
