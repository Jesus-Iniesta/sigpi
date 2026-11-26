"""Bandeja de solicitudes asignadas (S5-04, HU-04.6).

El técnico ve las solicitudes abiertas que tiene asignadas, de la más urgente a la
menos urgente: primero por prioridad (P1 antes que P4) y, dentro de la misma
prioridad, por la fecha compromiso más próxima. Cada renglón indica qué porcentaje del
tiempo de resolución ya se consumió y si la solicitud está en riesgo de vencer.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.core.config import settings
from app.models.enums import Priority, RequestStatus
from app.models.request import Request
from app.repositories.solicitud_repository import SolicitudRepository
from app.schemas.bandeja import BandejaElemento
from app.services.sla_clock_service import fecha_compromiso, minutos_efectivos

_ORDEN_PRIORIDAD = {Priority.P1: 0, Priority.P2: 1, Priority.P3: 2, Priority.P4: 3}
_SIN_FECHA = datetime.max.replace(tzinfo=UTC)


def _ahora() -> datetime:
    return datetime.now(UTC)


def porcentaje_consumido(request: Request, ahora: datetime) -> float | None:
    """Tiempo efectivo sobre el tiempo de resolución, en %; `None` si no tiene SLA."""
    version = request.service_level_version
    if version is None:
        return None
    return minutos_efectivos(request, ahora) / version.resolution_minutes * 100


def _clave_orden(elemento: BandejaElemento) -> tuple[int, datetime, str]:
    prioridad = _ORDEN_PRIORIDAD.get(elemento.prioridad, len(_ORDEN_PRIORIDAD))
    return (prioridad, elemento.fecha_compromiso or _SIN_FECHA, elemento.folio)


class BandejaService:
    def __init__(
        self,
        repository: SolicitudRepository,
        umbral: float | None = None,
        reloj: Callable[[], datetime] = _ahora,
    ) -> None:
        self._repository = repository
        self._umbral = settings.sla_warning_threshold if umbral is None else umbral
        self._reloj = reloj

    async def listar(
        self,
        *,
        technician_id: uuid.UUID | None,
        status: RequestStatus | None = None,
        priority: Priority | None = None,
    ) -> list[BandejaElemento]:
        """Solicitudes abiertas con asignación vigente, ordenadas por urgencia.

        Con `technician_id` solo las del técnico; con `None`, las de todo el equipo.
        """
        ahora = self._reloj()
        filas = await self._repository.list_asignadas(
            technician_id=technician_id, status=status, priority=priority
        )
        elementos = [self._elemento(request, categoria, ahora) for request, categoria in filas]
        return sorted(elementos, key=_clave_orden)

    def _elemento(
        self, request: Request, categoria: str | None, ahora: datetime
    ) -> BandejaElemento:
        porcentaje = porcentaje_consumido(request, ahora)
        return BandejaElemento(
            request_id=request.id,
            folio=request.folio,
            titulo=request.title,
            estatus=request.status,
            prioridad=request.priority,
            categoria=categoria,
            fecha_registro=request.created_at,
            fecha_compromiso=fecha_compromiso(request),
            porcentaje_consumido=None if porcentaje is None else round(porcentaje, 1),
            en_riesgo=porcentaje is not None and porcentaje >= self._umbral * 100,
        )
