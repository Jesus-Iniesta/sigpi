"""Acceso a datos de los avisos dentro de la aplicación (S4-05, HU-07.1).

Solo encapsula consultas: las reglas (quién recibe qué, cómo se redacta) viven en
`services/notificacion_service.py`.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.notification import Notification, NotificationTemplate
from app.models.request import Request, RequestAssignment


class NotificacionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, avisos: Sequence[Notification]) -> list[Notification]:
        """Guarda todos los avisos en una sola transacción."""
        self._session.add_all(avisos)
        await self._session.commit()
        return list(avisos)

    async def get_template(self, event_code: str) -> NotificationTemplate | None:
        result = await self._session.scalars(
            select(NotificationTemplate).where(NotificationTemplate.event_code == event_code)
        )
        return result.first()

    async def get_request_context(self, request_id: uuid.UUID) -> Request | None:
        """Solicitud con lo necesario para redactar el aviso (categoría, técnico, SLA)."""
        result = await self._session.scalars(
            select(Request)
            .where(Request.id == request_id)
            .options(
                selectinload(Request.category),
                selectinload(Request.service_level_version),
                selectinload(Request.sla_pauses),
                selectinload(Request.assignments).selectinload(RequestAssignment.technician),
            )
            .execution_options(populate_existing=True)
        )
        return result.first()

    async def list_for_recipient(
        self,
        recipient_id: uuid.UUID,
        *,
        only_unread: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """Avisos de una persona, del más reciente al más antiguo."""
        query = (
            select(Notification)
            .where(Notification.recipient_id == recipient_id)
            .options(selectinload(Notification.request))
            .order_by(Notification.created_at.desc(), Notification.id)
            .limit(limit)
            .offset(offset)
        )
        if only_unread:
            query = query.where(Notification.read_at.is_(None))
        return list(await self._session.scalars(query))

    async def count_unread(self, recipient_id: uuid.UUID) -> int:
        result = await self._session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.recipient_id == recipient_id, Notification.read_at.is_(None))
        )
        return int(result or 0)

    async def get_for_recipient(
        self, notification_id: uuid.UUID, recipient_id: uuid.UUID
    ) -> Notification | None:
        """Devuelve el aviso solo si pertenece a esa persona (nadie lee avisos ajenos)."""
        result = await self._session.scalars(
            select(Notification)
            .where(Notification.id == notification_id, Notification.recipient_id == recipient_id)
            .options(selectinload(Notification.request))
            .execution_options(populate_existing=True)
        )
        return result.first()

    async def mark_read(self, aviso: Notification, when: datetime) -> Notification:
        if aviso.read_at is None:
            aviso.read_at = when
            await self._session.commit()
        return aviso

    async def mark_all_read(self, recipient_id: uuid.UUID, when: datetime) -> int:
        result = await self._session.execute(
            update(Notification)
            .where(Notification.recipient_id == recipient_id, Notification.read_at.is_(None))
            .values(read_at=when)
        )
        await self._session.commit()
        return result.rowcount or 0
