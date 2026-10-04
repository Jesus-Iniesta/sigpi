"""Persistence gateway for service requests."""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.request import Request

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
