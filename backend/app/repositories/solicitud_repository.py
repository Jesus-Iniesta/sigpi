"""Persistence gateway for service requests."""

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.request import Request, RequestAssignment

_FOLIO_PATTERN = re.compile(r"^SIG-(\d+)$")


class SolicitudRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def next_folio(self) -> str:
        result = await self._session.scalars(
            select(Request.folio).where(Request.folio.like("SIG-%")).order_by(Request.folio.desc())
        )
        highest = 0
        for folio in result:
            match = _FOLIO_PATTERN.fullmatch(folio)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"SIG-{highest + 1:04d}"

    async def add(self, request: Request) -> Request:
        self._session.add(request)
        await self._session.commit()
        await self._session.refresh(request)
        return request

    async def list_by_requester(self, requester_id: uuid.UUID) -> list[Request]:
        """Solicitudes de una persona, de la más reciente a la más antigua."""
        result = await self._session.scalars(
            select(Request)
            .where(Request.requester_id == requester_id)
            .order_by(Request.created_at.desc(), Request.folio.desc())
        )
        return list(result)

    async def get_by_folio_for_requester(
        self, folio: str, requester_id: uuid.UUID
    ) -> Request | None:
        """Solicitud del folio indicado solo si pertenece a la persona; si no, `None`.

        El folio se compara sin distinguir mayúsculas. Se cargan la categoría, el SLA, las
        esperas, la bitácora y las asignaciones con su técnico para armar el detalle.
        """
        result = await self._session.scalars(
            select(Request)
            .where(
                func.upper(Request.folio) == folio.strip().upper(),
                Request.requester_id == requester_id,
            )
            .options(
                selectinload(Request.category),
                selectinload(Request.service_level_version),
                selectinload(Request.sla_pauses),
                selectinload(Request.logs),
                selectinload(Request.assignments).selectinload(RequestAssignment.technician),
            )
            .execution_options(populate_existing=True)
        )
        return result.first()
