"""Esquemas de la consulta del solicitante por folio (S4-01, HU-04.3).

El solicitante solo ve lo que le sirve para dar seguimiento: estatus, prioridad,
categoría, fecha compromiso, técnico vigente y un resumen de la bitácora. Las notas que
el técnico escribe en la bitácora son internas y no se exponen.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import Priority, RequestStatus
from app.models.request import Request
from app.services.sla_clock_service import fecha_compromiso
from app.services.sla_service import as_utc


class MiSolicitudResumen(BaseModel):
    """Renglón de la lista «Mis solicitudes»."""

    model_config = ConfigDict(from_attributes=True)

    folio: str
    title: str
    status: RequestStatus
    priority: Priority | None
    created_at: datetime


class MiSolicitudBitacoraEntrada(BaseModel):
    """Entrada resumida de la bitácora: acción, estatus nuevo y fecha (sin notas)."""

    model_config = ConfigDict(from_attributes=True)

    action: str
    new_status: RequestStatus | None
    created_at: datetime


class MiSolicitudDetalle(BaseModel):
    """Detalle de una solicitud propia consultada por folio."""

    folio: str
    title: str
    status: RequestStatus
    priority: Priority | None
    category: str | None
    due_at: datetime | None
    technician: str | None
    created_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None
    log: list[MiSolicitudBitacoraEntrada]

    @classmethod
    def desde_solicitud(cls, request: Request) -> "MiSolicitudDetalle":
        """Arma el detalle a partir de una solicitud con sus relaciones ya cargadas."""
        vigentes = [a for a in request.assignments if a.unassigned_at is None]
        actual = max(vigentes, key=lambda a: as_utc(a.assigned_at), default=None)
        entradas = sorted(request.logs, key=lambda entrada: as_utc(entrada.created_at))
        return cls(
            folio=request.folio,
            title=request.title,
            status=request.status,
            priority=request.priority,
            category=request.category.name if request.category else None,
            due_at=fecha_compromiso(request),
            technician=actual.technician.full_name if actual else None,
            created_at=request.created_at,
            resolved_at=request.resolved_at,
            closed_at=request.closed_at,
            log=[MiSolicitudBitacoraEntrada.model_validate(e) for e in entradas],
        )
