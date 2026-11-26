"""Consultas de solo lectura para los indicadores del servicio (S5-05)."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.request import Request


class IndicadorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def solicitudes_en_rango(self, inicio: datetime, fin: datetime) -> Sequence[Request]:
        """Solicitudes dadas de alta en [`inicio`, `fin`), con lo necesario para medirlas."""
        result = await self._session.scalars(
            select(Request)
            .where(Request.created_at >= inicio, Request.created_at < fin)
            .options(
                selectinload(Request.category),
                selectinload(Request.service_level_version),
                selectinload(Request.sla_pauses),
            )
            .order_by(Request.created_at, Request.folio)
        )
        return list(result)
