"""Esquemas de la bandeja de solicitudes asignadas (S5-04, HU-04.6)."""

from datetime import datetime

from pydantic import BaseModel

from app.models.enums import Priority, RequestStatus


class BandejaElemento(BaseModel):
    """Renglón de la bandeja: datos de la solicitud y avance de su reloj del SLA.

    `porcentaje_consumido` es el tiempo efectivo (sin esperas) sobre el tiempo de
    resolución comprometido; es `None` cuando la solicitud aún no tiene SLA. `en_riesgo`
    se enciende cuando ese porcentaje llega al umbral de riesgo (80 % por defecto).
    """

    folio: str
    titulo: str
    estatus: RequestStatus
    prioridad: Priority | None
    categoria: str | None
    fecha_registro: datetime
    fecha_compromiso: datetime | None
    porcentaje_consumido: float | None
    en_riesgo: bool
