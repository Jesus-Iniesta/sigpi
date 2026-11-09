"""Monitor del umbral de riesgo del SLA (S4-08, HU-07.2).

Cada cierto intervalo se revisan las solicitudes abiertas que tienen una versión de
acuerdo asignada. Si su tiempo efectivo (sin las esperas, HU-04.2) ya alcanzó el
umbral de riesgo (`sla_warning_threshold`, 80 % por defecto) del tiempo de
resolución comprometido para su prioridad, se marcan con `sla_risk_alerted_at`
para no volver a detectarlas.

Por cada solicitud detectada se emite el aviso de riesgo (S4-09) al técnico vigente y a
los jefes de servicio. Marcar y avisar se confirman en una sola transacción: si el aviso
falla, la solicitud no queda marcada y se reintenta en la siguiente vuelta.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger, log_event
from app.models.enums import RequestStatus
from app.models.request import Request
from app.services.notificacion_service import NotificacionService
from app.services.sla_clock_service import minutos_efectivos

logger = get_logger("sla_monitor")

ESTADOS_CERRADOS = (
    RequestStatus.RESOLVED,
    RequestStatus.CLOSED,
    RequestStatus.CLOSED_UNVERIFIED,
)

AlDetectar = Callable[[AsyncSession, Sequence[Request]], Awaitable[None]]
"""Punto de extensión: recibe la sesión de la vuelta y las solicitudes detectadas.

Se ejecuta dentro de la misma transacción que marca las solicitudes; si falla, la
vuelta se revierte y las solicitudes se vuelven a detectar en la siguiente.
"""


class SolicitudNoEncontradaError(NotFoundError):
    """La solicitud que se quiere marcar no existe."""


def _ahora() -> datetime:
    return datetime.now(UTC)


def alcanzo_umbral(request: Request, ahora: datetime, umbral: float) -> bool:
    """Indica si el tiempo efectivo ya llegó a `umbral` × tiempo de resolución comprometido."""
    version = request.service_level_version
    if version is None:
        return False
    return minutos_efectivos(request, ahora) >= umbral * version.resolution_minutes


async def registrar_en_log(_session: AsyncSession, solicitudes: Sequence[Request]) -> None:
    """Acción por defecto al detectar: solo deja constancia en el registro de eventos."""
    for request in solicitudes:
        log_event(
            logger,
            "sla_en_riesgo_detectada",
            level="WARNING",
            folio=request.folio,
            request_id=str(request.id),
        )


async def emitir_alertas_riesgo(session: AsyncSession, solicitudes: Sequence[Request]) -> None:
    """Acción por defecto al detectar: registra en el log y emite el aviso de riesgo.

    No confirma; el corte de cada aviso es el `sla_risk_alerted_at` que dejó la vuelta.
    """
    await registrar_en_log(session, solicitudes)
    servicio = NotificacionService(session)
    for request in solicitudes:
        await servicio.alerta_riesgo(request, request.sla_risk_alerted_at or _ahora())


class SlaMonitorService:
    def __init__(self, session: AsyncSession, umbral: float | None = None) -> None:
        self._session = session
        self._umbral = settings.sla_warning_threshold if umbral is None else umbral

    async def detectar_en_riesgo(self, ahora: datetime) -> list[Request]:
        """Solicitudes abiertas, con acuerdo, que llegaron al umbral y no se han alertado."""
        result = await self._session.scalars(
            select(Request)
            .where(
                Request.status.not_in(ESTADOS_CERRADOS),
                Request.service_level_version_id.is_not(None),
                Request.sla_risk_alerted_at.is_(None),
            )
            .options(
                selectinload(Request.sla_pauses),
                selectinload(Request.service_level_version),
            )
            .order_by(Request.created_at)
            .execution_options(populate_existing=True)
        )
        return [r for r in result if alcanzo_umbral(r, ahora, self._umbral)]

    async def marcar_alertada(self, request_id: uuid.UUID, ahora: datetime) -> Request:
        """Llena `sla_risk_alerted_at`. No confirma: el commit lo hace quien orquesta."""
        request = await self._session.get(Request, request_id)
        if request is None:
            raise SolicitudNoEncontradaError(f"No existe la solicitud {request_id}.")
        request.sla_risk_alerted_at = ahora
        return request

    async def ejecutar_vuelta(
        self,
        ahora: datetime | None = None,
        al_detectar: AlDetectar = emitir_alertas_riesgo,
    ) -> list[Request]:
        """Una vuelta del monitor: detecta, marca, avisa y confirma la transacción."""
        corte = ahora or _ahora()
        detectadas = await self.detectar_en_riesgo(corte)
        for request in detectadas:
            await self.marcar_alertada(request.id, corte)
        if detectadas:
            await al_detectar(self._session, detectadas)
        await self._session.commit()
        return detectadas


async def ejecutar_monitor(
    session_factory: async_sessionmaker[AsyncSession],
    intervalo_segundos: float,
    al_detectar: AlDetectar = emitir_alertas_riesgo,
) -> None:
    """Bucle del monitor: una vuelta por intervalo, cada una con su propia sesión.

    Si una vuelta falla, se registra el error y el bucle sigue en la siguiente.
    Termina solo cuando se cancela la tarea (al apagar la aplicación).
    """
    while True:
        try:
            async with session_factory() as session:
                await SlaMonitorService(session).ejecutar_vuelta(al_detectar=al_detectar)
        except Exception as exc:  # noqa: BLE001 - una vuelta fallida no detiene el monitor
            log_event(
                logger,
                "sla_monitor_vuelta_fallida",
                level="ERROR",
                error=type(exc).__name__,
                detalle=str(exc),
            )
        await asyncio.sleep(intervalo_segundos)
