"""Suspensión y reanudación del reloj del SLA (HU-04.2).

Cuando una solicitud pasa a «En espera» por una causa ajena al equipo de soporte
(un insumo externo o información pendiente del solicitante), el tiempo de
espera no cuenta contra el acuerdo de nivel de servicio. Cada espera se guarda
como un periodo con su inicio, su fin y su motivo; el tiempo efectivo de una
solicitud es el tiempo transcurrido menos la suma de esos periodos.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.estados import ESTADO_AL_REANUDAR, puede_reanudar, puede_suspender
from app.models.enums import RequestStatus, WaitReason
from app.models.request import Request, RequestLog, RequestSlaPause
from app.services.sla_service import as_utc


class SolicitudNoEncontradaError(LookupError):
    """La solicitud indicada no existe."""


class EstadoInvalidoError(ValueError):
    """La solicitud no está en un estado que permita la operación pedida."""


def _ahora() -> datetime:
    return datetime.now(UTC)


def _minutos(inicio: datetime, fin: datetime) -> float:
    return max((as_utc(fin) - as_utc(inicio)).total_seconds() / 60, 0.0)


def minutos_suspendidos(request: Request, ahora: datetime | None = None) -> float:
    """Suma los periodos de espera; el periodo abierto cuenta hasta `ahora`."""
    corte = ahora or _ahora()
    return sum(_minutos(p.started_at, p.ended_at or corte) for p in request.sla_pauses)


def minutos_efectivos(request: Request, ahora: datetime | None = None) -> float:
    """Minutos que cuentan para el SLA: transcurridos desde el alta, sin las esperas."""
    corte = ahora or _ahora()
    transcurridos = _minutos(request.created_at, corte)
    return max(transcurridos - minutos_suspendidos(request, corte), 0.0)


def minutos_restantes(
    request: Request, resolution_minutes: int, ahora: datetime | None = None
) -> float:
    """Minutos que faltan para vencer la resolución; negativo si ya venció."""
    return resolution_minutes - minutos_efectivos(request, ahora)


class SlaClockService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _load(self, request_id: uuid.UUID) -> Request:
        result = await self._session.scalars(
            select(Request)
            .where(Request.id == request_id)
            .options(selectinload(Request.sla_pauses), selectinload(Request.logs))
            .execution_options(populate_existing=True)
        )
        request = result.first()
        if request is None:
            raise SolicitudNoEncontradaError(f"request {request_id} does not exist")
        return request

    async def suspender(
        self,
        request_id: uuid.UUID,
        author_id: uuid.UUID,
        reason: WaitReason,
        detail: str | None = None,
        ahora: datetime | None = None,
    ) -> Request:
        """Pasa la solicitud a «En espera» y detiene el reloj del SLA."""
        request = await self._load(request_id)
        if not puede_suspender(request.status):
            raise EstadoInvalidoError(
                f"una solicitud en estado {request.status} no puede pasar a «En espera»"
            )
        corte = ahora or _ahora()
        previous = request.status
        request.status = RequestStatus.WAITING
        request.sla_pauses.append(
            RequestSlaPause(
                reason=reason,
                detail=detail,
                started_by_id=author_id,
                started_at=corte,
            )
        )
        request.logs.append(
            RequestLog(
                author_id=author_id,
                previous_status=previous,
                new_status=RequestStatus.WAITING,
                action="Reloj del SLA suspendido",
                notes=_nota(reason, detail),
            )
        )
        await self._session.commit()
        return await self._load(request_id)

    async def reanudar(
        self,
        request_id: uuid.UUID,
        author_id: uuid.UUID,
        ahora: datetime | None = None,
    ) -> Request:
        """Saca la solicitud de «En espera» y reanuda el reloj del SLA."""
        request = await self._load(request_id)
        abierta = next((p for p in request.sla_pauses if p.ended_at is None), None)
        if not puede_reanudar(request.status) or abierta is None:
            raise EstadoInvalidoError("la solicitud no está en «En espera»")
        corte = ahora or _ahora()
        abierta.ended_at = corte
        abierta.ended_by_id = author_id
        request.status = ESTADO_AL_REANUDAR
        request.logs.append(
            RequestLog(
                author_id=author_id,
                previous_status=RequestStatus.WAITING,
                new_status=ESTADO_AL_REANUDAR,
                action="Reloj del SLA reanudado",
                notes=f"Tiempo en espera: {_minutos(abierta.started_at, corte):.0f} min.",
            )
        )
        await self._session.commit()
        return await self._load(request_id)


_MOTIVOS = {
    WaitReason.EXTERNAL_INPUT: "insumo externo",
    WaitReason.USER_INFORMATION: "información pendiente del solicitante",
}


def _nota(reason: WaitReason, detail: str | None) -> str:
    base = f"Motivo: {_MOTIVOS[reason]}."
    return f"{base} {detail}" if detail else base
