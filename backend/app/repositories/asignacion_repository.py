"""Consultas de la asignación de técnicos (S5-03, HU-03.1).

Solo acceso a datos: el puntaje vive en `domain/asignacion.py` y la orquestación en
`services/asignacion_service.py`. No confirma: el servicio cierra la transacción.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.asignacion import ESTADOS_NO_ASIGNABLES
from app.models.enums import UserType
from app.models.identity import User
from app.models.request import Request, RequestAssignment


class AsignacionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_request(self, request_id: uuid.UUID) -> Request | None:
        result = await self._session.scalars(
            select(Request)
            .where(Request.id == request_id)
            .execution_options(populate_existing=True)
        )
        return result.first()

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def list_technicians(self) -> list[User]:
        """Técnicos activos con sus especialidades y su turno."""
        result = await self._session.scalars(
            select(User)
            .where(User.user_type == UserType.TECHNICAL, User.is_active.is_(True))
            .options(selectinload(User.specialties), selectinload(User.shift))
            .order_by(User.full_name, User.id)
        )
        return list(result)

    async def active_load(self) -> dict[uuid.UUID, int]:
        """Solicitudes activas (no resueltas ni cerradas) con asignación vigente, por técnico."""
        result = await self._session.execute(
            select(RequestAssignment.technician_id, func.count(RequestAssignment.id))
            .join(Request, Request.id == RequestAssignment.request_id)
            .where(
                RequestAssignment.unassigned_at.is_(None),
                Request.status.not_in(list(ESTADOS_NO_ASIGNABLES)),
            )
            .group_by(RequestAssignment.technician_id)
        )
        return {technician_id: int(total) for technician_id, total in result.all()}

    async def close_current(self, request_id: uuid.UUID, when: datetime) -> None:
        """Marca como terminadas las asignaciones vigentes de la solicitud."""
        await self._session.execute(
            update(RequestAssignment)
            .where(
                RequestAssignment.request_id == request_id,
                RequestAssignment.unassigned_at.is_(None),
            )
            .values(unassigned_at=when)
            .execution_options(synchronize_session="fetch")
        )

    async def add(self, assignment: RequestAssignment) -> RequestAssignment:
        self._session.add(assignment)
        await self._session.flush()
        return assignment
