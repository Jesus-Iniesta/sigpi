"""Persistence gateway for service requests."""

import re
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import Categoria
from app.models.enums import Priority, RequestStatus
from app.models.identity import User
from app.models.request import Request, RequestAssignment

_FOLIO_PATTERN = re.compile(r"^SIG-(\d+)$")


def _patron_busqueda(texto: str) -> str:
    """Patrón `ILIKE` que trata `%` y `_` del texto como caracteres literales."""
    escapado = texto.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


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

    async def search(
        self,
        *,
        texto: str | None,
        status: RequestStatus | None,
        priority: Priority | None,
        requester_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[Request, str | None, str | None]], int]:
        """Listado paginado, de la más reciente a la más antigua.

        Devuelve filas `(solicitud, nombre de la categoría, nombre del solicitante)` y el
        total de coincidencias. El texto se busca, sin distinguir mayúsculas, en el folio,
        el título, la descripción, la matrícula o clave del solicitante y su nombre.
        `requester_id` limita el listado a las solicitudes de una persona.
        """
        filtros = []
        if requester_id is not None:
            filtros.append(Request.requester_id == requester_id)
        if status is not None:
            filtros.append(Request.status == status.value)
        if priority is not None:
            filtros.append(Request.priority == priority.value)
        if texto and texto.strip():
            patron = _patron_busqueda(texto)
            filtros.append(
                or_(
                    Request.folio.ilike(patron, escape="\\"),
                    Request.title.ilike(patron, escape="\\"),
                    Request.description.ilike(patron, escape="\\"),
                    Request.requester_institutional_id.ilike(patron, escape="\\"),
                    User.full_name.ilike(patron, escape="\\"),
                )
            )

        total = await self._session.scalar(
            select(func.count(Request.id))
            .select_from(Request)
            .outerjoin(User, Request.requester_id == User.id)
            .where(*filtros)
        )
        filas = await self._session.execute(
            select(Request, Categoria.name, User.full_name)
            .outerjoin(Categoria, Request.category_id == Categoria.id)
            .outerjoin(User, Request.requester_id == User.id)
            .where(*filtros)
            .order_by(Request.created_at.desc(), Request.folio.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(r, categoria, nombre) for r, categoria, nombre in filas.all()], total or 0

    async def list_asignadas(
        self,
        *,
        technician_id: uuid.UUID | None,
        status: RequestStatus | None,
        priority: Priority | None,
    ) -> list[tuple[Request, str | None]]:
        """Solicitudes abiertas con una asignación vigente, con el nombre de su categoría.

        Una asignación es vigente mientras `unassigned_at` sea nulo. Con `technician_id`
        solo se devuelven las asignadas a ese técnico; sin él, todas las que tengan una
        asignación vigente. Las cerradas (con o sin verificación) se excluyen. Se cargan
        el SLA y las esperas para calcular la fecha compromiso; el orden lo da el servicio.
        """
        vigente = select(RequestAssignment.id).where(
            RequestAssignment.request_id == Request.id,
            RequestAssignment.unassigned_at.is_(None),
        )
        if technician_id is not None:
            vigente = vigente.where(RequestAssignment.technician_id == technician_id)
        filtros = [
            vigente.exists(),
            Request.status.not_in([RequestStatus.CLOSED, RequestStatus.CLOSED_UNVERIFIED]),
        ]
        if status is not None:
            filtros.append(Request.status == status.value)
        if priority is not None:
            filtros.append(Request.priority == priority.value)

        filas = await self._session.execute(
            select(Request, Categoria.name)
            .outerjoin(Categoria, Request.category_id == Categoria.id)
            .where(*filtros)
            .options(
                selectinload(Request.service_level_version),
                selectinload(Request.sla_pauses),
            )
        )
        return [(r, categoria) for r, categoria in filas.all()]
