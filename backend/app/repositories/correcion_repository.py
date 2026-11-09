"""Acceso a datos de las correcciones de clasificación (S4-16, HU-02.2).

Cuando una persona revisora corrige una clasificación de baja confianza, la corrección se
guarda como un ejemplo verificado para reentrenar el clasificador (RN-07, HU-12.2).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.classification import ClassificationCorrection, ClassificationResult

# Valor de la columna `source` cuando el ejemplo sale de una corrección humana. El conjunto
# de datos inicial (S4-11) usa «equipo»; así se distinguen al unirlos para reentrenar.
FUENTE_CORRECCION = "correccion"


@dataclass(frozen=True, slots=True)
class EjemploReentrenamiento:
    """Una solicitud con su etiqueta verificada por una persona."""

    correction_id: uuid.UUID
    result_id: uuid.UUID
    request_id: uuid.UUID
    folio: str
    title: str
    description: str
    category_id: uuid.UUID
    category_name: str
    urgency: int
    impact: int
    corrected_at: datetime

    @property
    def text(self) -> str:
        """Texto que lee el clasificador: título y descripción de la solicitud."""
        return f"{self.title.strip().rstrip('.')}. {self.description.strip()}"

    def to_dataset_row(self) -> dict[str, str | int]:
        """Fila con las mismas columnas que `ml/data/dataset_v1.csv`."""
        return {
            "id": f"COR-{self.correction_id.hex[:8]}",
            "text": self.text,
            "category": self.category_name,
            "urgency": self.urgency,
            "impact": self.impact,
            "source": FUENTE_CORRECCION,
        }


class CorreccionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, correccion: ClassificationCorrection) -> ClassificationCorrection:
        """Agrega la corrección a la transacción en curso sin confirmarla."""
        self._session.add(correccion)
        await self._session.flush()
        await self._session.refresh(correccion)
        return correccion

    async def list_by_result(self, result_id: uuid.UUID) -> list[ClassificationCorrection]:
        """Correcciones de una clasificación, de la más antigua a la más reciente."""
        result = await self._session.scalars(
            select(ClassificationCorrection)
            .where(ClassificationCorrection.result_id == result_id)
            .order_by(ClassificationCorrection.created_at, ClassificationCorrection.id)
        )
        return list(result)

    async def get_latest_for_result(self, result_id: uuid.UUID) -> ClassificationCorrection | None:
        """La corrección vigente de una clasificación, o `None` si nadie la ha corregido."""
        correcciones = await self.list_by_result(result_id)
        return correcciones[-1] if correcciones else None

    async def list_training_examples(
        self, *, since: datetime | None = None
    ) -> list[EjemploReentrenamiento]:
        """Ejemplos de reentrenamiento a partir de las correcciones guardadas.

        - Si una clasificación se corrigió varias veces, solo cuenta la última.
        - Un valor que la persona no cambió (`corrected_*` vacío) conserva el de la
          predicción: revisar y confirmar también es una etiqueta verificada.
        - Si no hay categoría ni en la corrección ni en la predicción, se omite: sin
          categoría no hay etiqueta con la que entrenar.
        - `since` limita a las correcciones hechas desde esa fecha (inclusive).
        """
        query = (
            select(ClassificationCorrection)
            .options(
                selectinload(ClassificationCorrection.result).selectinload(
                    ClassificationResult.request
                ),
                selectinload(ClassificationCorrection.result).selectinload(
                    ClassificationResult.category
                ),
                selectinload(ClassificationCorrection.corrected_category),
            )
            .order_by(ClassificationCorrection.created_at, ClassificationCorrection.id)
            .execution_options(populate_existing=True)
        )
        if since is not None:
            query = query.where(ClassificationCorrection.created_at >= since)

        ultimas: dict[uuid.UUID, ClassificationCorrection] = {}
        for correccion in await self._session.scalars(query):
            ultimas[correccion.result_id] = correccion  # la más reciente sobrescribe

        ejemplos: list[EjemploReentrenamiento] = []
        for correccion in sorted(ultimas.values(), key=lambda c: (c.created_at, c.id)):
            resultado = correccion.result
            categoria = correccion.corrected_category or resultado.category
            if categoria is None:
                continue
            solicitud = resultado.request
            ejemplos.append(
                EjemploReentrenamiento(
                    correction_id=correccion.id,
                    result_id=resultado.id,
                    request_id=solicitud.id,
                    folio=solicitud.folio,
                    title=solicitud.title,
                    description=solicitud.description,
                    category_id=categoria.id,
                    category_name=categoria.name,
                    urgency=(
                        correccion.corrected_urgency
                        if correccion.corrected_urgency is not None
                        else resultado.urgency
                    ),
                    impact=(
                        correccion.corrected_impact
                        if correccion.corrected_impact is not None
                        else resultado.impact
                    ),
                    corrected_at=correccion.created_at,
                )
            )
        return ejemplos
