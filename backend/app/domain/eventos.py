"""Catálogo de eventos que generan aviso (S4-04, HU-07.1).

Fuente única de verdad: los códigos de evento, su importancia y quién recibe el aviso.
Las reglas son puras: no consultan la base de datos ni conocen el ORM.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.core.permissions import RoleName
from app.models.enums import NotificationImportance


class EventoAviso(StrEnum):
    SOLICITUD_REGISTRADA = "request_registered"
    SOLICITUD_ASIGNADA = "request_assigned"
    ESTATUS_CAMBIADO = "request_status_changed"
    SOLICITUD_RESUELTA = "request_resolved"
    SOLICITUD_CERRADA = "request_closed"
    RIESGO_SLA = "sla_risk"
    P1_SIN_ASIGNAR = "p1_unassigned"


class Destinatario(StrEnum):
    """Papel que juega cada destinatario respecto de la solicitud."""

    SOLICITANTE = "solicitante"
    TECNICO = "tecnico"
    JEFES = "jefes"  # usuarios con el rol `service_manager`


# Rol que identifica a los jefes de servicio que reciben avisos de escalamiento.
ROL_JEFES = RoleName.SERVICE_MANAGER


@dataclass(frozen=True, slots=True)
class ReglaEvento:
    importancia: NotificationImportance
    destinatarios: tuple[Destinatario, ...]


CATALOGO_EVENTOS: dict[EventoAviso, ReglaEvento] = {
    EventoAviso.SOLICITUD_REGISTRADA: ReglaEvento(
        NotificationImportance.NORMAL, (Destinatario.SOLICITANTE,)
    ),
    EventoAviso.SOLICITUD_ASIGNADA: ReglaEvento(
        NotificationImportance.NORMAL, (Destinatario.SOLICITANTE, Destinatario.TECNICO)
    ),
    EventoAviso.ESTATUS_CAMBIADO: ReglaEvento(
        NotificationImportance.NORMAL, (Destinatario.SOLICITANTE,)
    ),
    EventoAviso.SOLICITUD_RESUELTA: ReglaEvento(
        NotificationImportance.NORMAL, (Destinatario.SOLICITANTE,)
    ),
    EventoAviso.SOLICITUD_CERRADA: ReglaEvento(
        NotificationImportance.NORMAL, (Destinatario.SOLICITANTE, Destinatario.TECNICO)
    ),
    EventoAviso.RIESGO_SLA: ReglaEvento(
        NotificationImportance.HIGH, (Destinatario.TECNICO, Destinatario.JEFES)
    ),
    EventoAviso.P1_SIN_ASIGNAR: ReglaEvento(NotificationImportance.HIGH, (Destinatario.JEFES,)),
}


def importancia(evento: EventoAviso | str) -> NotificationImportance:
    """Importancia con la que se guarda el aviso del evento."""
    return CATALOGO_EVENTOS[EventoAviso(evento)].importancia


def destinatarios(
    evento: EventoAviso | str,
    solicitante_id: uuid.UUID | None,
    tecnico_id: uuid.UUID | None,
    jefes_ids: list[uuid.UUID] | tuple[uuid.UUID, ...] | None = None,
) -> list[uuid.UUID]:
    """Usuarios que reciben el aviso del evento, sin `None` ni repetidos y en orden estable."""
    candidatos: dict[Destinatario, list[uuid.UUID | None]] = {
        Destinatario.SOLICITANTE: [solicitante_id],
        Destinatario.TECNICO: [tecnico_id],
        Destinatario.JEFES: list(jefes_ids or ()),
    }
    regla = CATALOGO_EVENTOS[EventoAviso(evento)]
    elegidos = (uid for papel in regla.destinatarios for uid in candidatos[papel])
    return list(dict.fromkeys(uid for uid in elegidos if uid is not None))
