"""Acceso a datos de las correcciones de clasificación (S4-16, HU-02.2 AC2).

No confirma la transacción (COR-02): lo hace `services/revision_service.py`.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import Categoria
from app.models.classification import ClassificationCorrection, ClassificationResult
from app.models.request import Request


@dataclass(frozen=True)
class EjemploCorregido:
    """Una solicitud con las etiquetas que le dio una persona revisora."""

    folio: str
    titulo: str
    descripcion: str
    categoria: str
    urgencia: int
    impacto: int


class CorreccionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_resultado(self, result_id: uuid.UUID) -> ClassificationResult | None:
        """Resultado de clasificación con su solicitud cargada."""
        return await self._session.scalar(
            select(ClassificationResult)
            .where(ClassificationResult.id == result_id)
            .options(selectinload(ClassificationResult.request))
        )

    async def get_categoria(self, category_id: uuid.UUID) -> Categoria | None:
        return await self._session.get(Categoria, category_id)

    async def existe_para(self, result_id: uuid.UUID) -> bool:
        """Indica si el resultado ya tiene una corrección guardada."""
        encontrado = await self._session.scalar(
            select(ClassificationCorrection.id)
            .where(ClassificationCorrection.result_id == result_id)
            .limit(1)
        )
        return encontrado is not None

    async def add(self, correccion: ClassificationCorrection) -> ClassificationCorrection:
        """Agrega la corrección a la transacción en curso sin confirmarla."""
        self._session.add(correccion)
        await self._session.flush()
        return correccion

    async def ejemplos_para_reentrenamiento(self) -> list[EjemploCorregido]:
        """Texto de cada solicitud corregida con sus etiquetas corregidas.

        Si una solicitud tiene varias correcciones, se usa la más reciente. Se omiten las
        correcciones sin categoría, urgencia o impacto, que no sirven como ejemplo.
        """
        filas = await self._session.execute(
            select(
                Request.id,
                Request.folio,
                Request.title,
                Request.description,
                Categoria.name,
                ClassificationCorrection.corrected_urgency,
                ClassificationCorrection.corrected_impact,
            )
            .join(
                ClassificationResult,
                ClassificationResult.id == ClassificationCorrection.result_id,
            )
            .join(Request, Request.id == ClassificationResult.request_id)
            .join(Categoria, Categoria.id == ClassificationCorrection.corrected_category_id)
            .where(
                ClassificationCorrection.corrected_urgency.is_not(None),
                ClassificationCorrection.corrected_impact.is_not(None),
            )
            .order_by(ClassificationCorrection.created_at, ClassificationCorrection.id)
        )
        ultimos: dict[uuid.UUID, EjemploCorregido] = {}
        for request_id, folio, titulo, descripcion, categoria, urgencia, impacto in filas:
            # Vienen de la más antigua a la más reciente: la última de cada solicitud gana.
            ultimos[request_id] = EjemploCorregido(
                folio=folio,
                titulo=titulo,
                descripcion=descripcion,
                categoria=categoria,
                urgencia=urgencia,
                impacto=impacto,
            )
        return sorted(ultimos.values(), key=lambda e: e.folio)
