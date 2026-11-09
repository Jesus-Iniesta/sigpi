"""Notificaciones dentro de la aplicación (S4-05, HU-07.1).

Cuando ocurre un evento del ciclo de vida de una solicitud, el servicio redacta un aviso
con folio, categoría, prioridad, técnico y fecha compromiso y lo guarda para cada
destinatario. La campana de la interfaz (S4-06) lo consulta; no hay correo (queda fuera
del alcance del proyecto escolar, ver HU-07.3).
"""

import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.logging import get_logger, log_event
from app.models.enums import (
    NotificationChannel,
    NotificationImportance,
    NotificationStatus,
    RequestStatus,
)
from app.models.notification import Notification
from app.models.request import Request
from app.repositories.notificacion_repository import NotificacionRepository
from app.services.sla_clock_service import fecha_compromiso
from app.services.sla_service import as_utc

logger = get_logger("notificaciones")

SIN_DATO = "—"

# Códigos de evento. Deben coincidir con el catálogo de S4-04 (Emmanuel).
EVENTO_SOLICITUD_REGISTRADA = "request_registered"
EVENTO_SOLICITUD_ASIGNADA = "request_assigned"
EVENTO_ESTATUS_CAMBIADO = "request_status_changed"
EVENTO_SOLICITUD_RESUELTA = "request_resolved"
EVENTO_SOLICITUD_CERRADA = "request_closed"
EVENTO_RIESGO_SLA = "sla_risk"
EVENTO_P1_SIN_ASIGNAR = "p1_unassigned"

# código de evento -> (asunto, cuerpo). Los campos entre llaves salen de `_contexto`.
_PLANTILLAS_RESPALDO: dict[str, tuple[str, str]] = {
    EVENTO_SOLICITUD_REGISTRADA: (
        "Solicitud {folio} registrada",
        (
            "Registramos tu solicitud «{titulo}».\n"
            "Folio: {folio} · Categoría: {categoria} · Prioridad: {prioridad}\n"
            "Técnico: {tecnico} · Fecha compromiso: {fecha_compromiso}"
        ),
    ),
    EVENTO_SOLICITUD_ASIGNADA: (
        "Solicitud {folio} asignada",
        (
            "La solicitud «{titulo}» tiene técnico asignado.\n"
            "Folio: {folio} · Categoría: {categoria} · Prioridad: {prioridad}\n"
            "Técnico: {tecnico} · Fecha compromiso: {fecha_compromiso}"
        ),
    ),
    EVENTO_ESTATUS_CAMBIADO: (
        "Solicitud {folio}: {estado}",
        (
            "La solicitud «{titulo}» cambió de estatus a {estado}.\n"
            "Folio: {folio} · Categoría: {categoria} · Prioridad: {prioridad}\n"
            "Técnico: {tecnico} · Fecha compromiso: {fecha_compromiso}"
        ),
    ),
    EVENTO_SOLICITUD_RESUELTA: (
        "Solicitud {folio} resuelta",
        (
            "El técnico resolvió «{titulo}». Confirma si la solución funcionó.\n"
            "Folio: {folio} · Categoría: {categoria} · Prioridad: {prioridad}\n"
            "Técnico: {tecnico} · Fecha compromiso: {fecha_compromiso}"
        ),
    ),
    EVENTO_SOLICITUD_CERRADA: (
        "Solicitud {folio} cerrada",
        (
            "Cerramos la solicitud «{titulo}».\n"
            "Folio: {folio} · Categoría: {categoria} · Prioridad: {prioridad}\n"
            "Técnico: {tecnico} · Fecha compromiso: {fecha_compromiso}"
        ),
    ),
    EVENTO_RIESGO_SLA: (
        "Riesgo de incumplir {folio}",
        (
            "La solicitud «{titulo}» ya consumió el 80 % del tiempo comprometido.\n"
            "Folio: {folio} · Prioridad: {prioridad} · Técnico: {tecnico}\n"
            "Fecha compromiso: {fecha_compromiso}"
        ),
    ),
    EVENTO_P1_SIN_ASIGNAR: (
        "Solicitud crítica {folio} sin asignar",
        (
            "La solicitud P1 «{titulo}» lleva cinco minutos sin técnico asignado.\n"
            "Folio: {folio} · Categoría: {categoria} · Fecha compromiso: {fecha_compromiso}"
        ),
    ),
}

# Mismos textos que `STATUS_LABELS` del frontend (features/requests/request-labels.ts).
_ETIQUETAS_ESTATUS: dict[str, str] = {
    RequestStatus.REGISTERED: "Registrada",
    RequestStatus.PENDING_VERIFICATION: "Por verificar",
    RequestStatus.CLASSIFIED: "Clasificada",
    RequestStatus.PENDING_REVIEW: "En revisión",
    RequestStatus.ASSIGNED: "Asignada",
    RequestStatus.IN_PROGRESS: "En proceso",
    RequestStatus.WAITING: "En espera",
    RequestStatus.ESCALATED: "Escalada",
    RequestStatus.RESOLVED: "Resuelta",
    RequestStatus.CLOSED: "Cerrada",
    RequestStatus.CLOSED_UNVERIFIED: "Cerrada sin verificar",
}

EVENTOS_CONOCIDOS: frozenset[str] = frozenset(_PLANTILLAS_RESPALDO)

_ASUNTO_MAX = 240  # longitud de `notifications.subject`


class _SafeDict(dict[str, str]):
    """Un campo que falte en el contexto se muestra como «—» en lugar de fallar."""

    def __missing__(self, key: str) -> str:
        return SIN_DATO


def _ahora() -> datetime:
    return datetime.now(UTC)


def _formatear_fecha(value: datetime | None) -> str:
    if value is None:
        return SIN_DATO
    return as_utc(value).strftime("%d/%m/%Y %H:%M UTC")


def _tecnico_vigente(request: Request) -> str:
    vigentes = [a for a in request.assignments if a.unassigned_at is None]
    if not vigentes:
        return "Sin asignar"
    actual = max(vigentes, key=lambda a: as_utc(a.assigned_at))
    return actual.technician.full_name


def _contexto(request: Request, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    datos = {
        "folio": request.folio,
        "titulo": request.title,
        "categoria": request.category.name if request.category else "Sin clasificar",
        "prioridad": str(request.priority) if request.priority else SIN_DATO,
        "tecnico": _tecnico_vigente(request),
        "estado": _ETIQUETAS_ESTATUS.get(request.status, str(request.status)),
        "fecha_compromiso": _formatear_fecha(fecha_compromiso(request)),
    }
    if extra:
        datos.update(extra)
    return datos


class NotificacionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = NotificacionRepository(session)

    # ------------------------------------------------------------------ emisión

    async def notificar_evento(
        self,
        event_code: str,
        request_id: uuid.UUID,
        recipient_ids: Iterable[uuid.UUID],
        *,
        importance: NotificationImportance = NotificationImportance.NORMAL,
        extra: Mapping[str, str] | None = None,
        ahora: datetime | None = None,
    ) -> list[Notification]:
        """Guarda un aviso por destinatario para un evento de una solicitud.

        Los destinatarios repetidos se avisan una sola vez. Si la lista queda vacía no se
        guarda nada. Un código sin plantilla es un error de programación: se rechaza.
        """
        destinatarios = list(dict.fromkeys(recipient_ids))
        if not destinatarios:
            return []

        plantilla = await self._repository.get_template(event_code)
        if plantilla is not None:
            asunto_tpl, cuerpo_tpl = plantilla.subject_template, plantilla.body_template
        elif event_code in _PLANTILLAS_RESPALDO:
            asunto_tpl, cuerpo_tpl = _PLANTILLAS_RESPALDO[event_code]
        else:
            raise BusinessRuleError(f"El evento «{event_code}» no tiene plantilla de aviso.")

        request = await self._repository.get_request_context(request_id)
        if request is None:
            raise NotFoundError(f"La solicitud {request_id} no existe.")

        datos = _SafeDict(_contexto(request, extra))
        asunto = asunto_tpl.format_map(datos)[:_ASUNTO_MAX]
        cuerpo = cuerpo_tpl.format_map(datos)
        corte = ahora or _ahora()

        avisos = [
            Notification(
                template_id=plantilla.id if plantilla is not None else None,
                request_id=request.id,
                recipient_id=destinatario,
                channel=NotificationChannel.IN_APP,
                subject=asunto,
                body=cuerpo,
                status=NotificationStatus.SENT,
                importance=importance,
                sent_at=corte,
                created_at=corte,
            )
            for destinatario in destinatarios
        ]
        guardados = await self._repository.add_many(avisos)
        log_event(
            logger,
            "aviso_emitido",
            evento=event_code,
            folio=request.folio,
            destinatarios=len(guardados),
            importancia=str(importance),
        )
        return guardados

    # ----------------------------------------------------------------- consulta

    async def listar(
        self,
        user_id: uuid.UUID,
        *,
        only_unread: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        return await self._repository.list_for_recipient(
            user_id, only_unread=only_unread, limit=limit, offset=offset
        )

    async def contar_no_leidos(self, user_id: uuid.UUID) -> int:
        return await self._repository.count_unread(user_id)

    async def marcar_leido(
        self, user_id: uuid.UUID, notification_id: uuid.UUID, ahora: datetime | None = None
    ) -> Notification:
        aviso = await self._repository.get_for_recipient(notification_id, user_id)
        if aviso is None:
            raise NotFoundError("El aviso no existe.")
        return await self._repository.mark_read(aviso, ahora or _ahora())

    async def marcar_todos_leidos(self, user_id: uuid.UUID, ahora: datetime | None = None) -> int:
        return await self._repository.mark_all_read(user_id, ahora or _ahora())
