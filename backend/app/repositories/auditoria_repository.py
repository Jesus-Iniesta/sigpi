"""Persistence gateway for the append-only audit trail."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auditoria import Auditoria


class AuditoriaRepository:
    """Stores and queries audit entries without exposing mutation methods."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: Auditoria) -> Auditoria:
        self._session.add(entry)
        await self._session.commit()
        await self._session.refresh(entry)
        return entry

    async def list_for_entity(
        self,
        *,
        entity_type: str,
        entity_id: str,
    ) -> list[Auditoria]:
        result = await self._session.scalars(
            select(Auditoria)
            .where(
                Auditoria.entity_type == entity_type,
                Auditoria.entity_id == entity_id,
            )
            .order_by(Auditoria.created_at, Auditoria.id)
        )
        return list(result)

    async def list_for_actor(
        self,
        *,
        actor_id: uuid.UUID,
        since: datetime | None = None,
    ) -> list[Auditoria]:
        query = select(Auditoria).where(Auditoria.actor_id == actor_id)
        if since is not None:
            query = query.where(Auditoria.created_at >= since)
        result = await self._session.scalars(query.order_by(Auditoria.created_at, Auditoria.id))
        return list(result)
