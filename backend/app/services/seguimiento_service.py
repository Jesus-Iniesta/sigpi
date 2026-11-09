"""Seguimiento y resolución de solicitudes (HU-04.1).

Cada acción del técnico deja una entrada en la bitácora, que solo admite altas: el
historial nunca se reescribe. El diagnóstico y la solución vigentes se guardan además
en la solicitud para mostrarlos sin recorrer toda la bitácora.

Cada cambio de estatus avisa a sus destinatarios (S4-07, HU-07.1): iniciar la atención
emite `request_status_changed`; resolver, `request_resolved`, y confirmar,
`request_closed`. El aviso se guarda en la misma transacción que el cambio: si su
escritura falla, el cambio tampoco se guarda.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.estados import puede_diagnosticar, puede_iniciar, puede_resolver
from app.domain.eventos import EventoAviso
from app.models.enums import RequestStatus
from app.models.request import Request, RequestLog
from app.services.notificacion_service import NotificacionService
from app.services.sla_clock_service import (
    EstadoInvalidoError,
    SolicitudNoEncontradaError,
    minutos_efectivos,
)


def _ahora() -> datetime:
    return datetime.now(UTC)


class SeguimientoService:
    def __init__(
        self, session: AsyncSession, notificaciones: NotificacionService | None = None
    ) -> None:
        self._session = session
        self._notificaciones = notificaciones or NotificacionService(session)

    async def _confirmar_con_aviso(
        self, request_id: uuid.UUID, evento: EventoAviso, corte: datetime
    ) -> Request:
        """Guarda el aviso del evento y confirma el cambio y el aviso en una transacción."""
        try:
            await self._session.flush()
            await self._notificaciones.emitir(evento, request_id, ahora=corte)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return await self._load(request_id)

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

    async def obtener(self, request_id: uuid.UUID) -> Request:
        """Devuelve una solicitud con su diagnóstico y solución vigentes (detalle, S3-13)."""
        return await self._load(request_id)

    async def registrar_diagnostico(
        self, request_id: uuid.UUID, author_id: uuid.UUID, diagnosis: str
    ) -> Request:
        """Guarda el diagnóstico vigente; cada versión queda además en la bitácora."""
        request = await self._load(request_id)
        if not puede_diagnosticar(request.status):
            raise EstadoInvalidoError(
                f"una solicitud en estado {request.status} no admite diagnóstico"
            )
        accion = "Diagnóstico actualizado" if request.diagnosis else "Diagnóstico registrado"
        request.diagnosis = diagnosis
        request.logs.append(
            RequestLog(
                author_id=author_id,
                previous_status=request.status,
                new_status=request.status,
                action=accion,
                notes=diagnosis,
            )
        )
        await self._session.commit()
        return await self._load(request_id)

    async def iniciar_atencion(
        self, request_id: uuid.UUID, author_id: uuid.UUID, ahora: datetime | None = None
    ) -> Request:
        """Pasa la solicitud a «En proceso» y marca la primera respuesta."""
        request = await self._load(request_id)
        if not puede_iniciar(request.status):
            raise EstadoInvalidoError(
                f"una solicitud en estado {request.status} no puede iniciar su atención"
            )
        corte = ahora or _ahora()
        previous = request.status
        request.status = RequestStatus.IN_PROGRESS
        if request.first_response_at is None:
            request.first_response_at = corte
        request.logs.append(
            RequestLog(
                author_id=author_id,
                previous_status=previous,
                new_status=RequestStatus.IN_PROGRESS,
                action="Atención iniciada",
            )
        )
        return await self._confirmar_con_aviso(request_id, EventoAviso.ESTATUS_CAMBIADO, corte)

    async def resolver(
        self,
        request_id: uuid.UUID,
        author_id: uuid.UUID,
        solution: str,
        diagnosis: str | None = None,
        ahora: datetime | None = None,
    ) -> Request:
        """Marca la solicitud como resuelta y calcula su tiempo efectivo de resolución.

        El tiempo no cuenta los periodos en espera. La solicitud queda en «Resuelta» y la
        bitácora anota que se solicita al solicitante confirmar la solución.
        """
        request = await self._load(request_id)
        if not puede_resolver(request.status):
            raise EstadoInvalidoError(
                f"una solicitud en estado {request.status} no puede resolverse"
            )
        corte = ahora or _ahora()
        previous = request.status
        if diagnosis is not None:
            request.diagnosis = diagnosis
        request.solution = solution
        request.status = RequestStatus.RESOLVED
        request.resolved_at = corte
        if request.first_response_at is None:
            request.first_response_at = corte
        request.resolution_minutes = round(minutos_efectivos(request, corte))
        request.logs.append(
            RequestLog(
                author_id=author_id,
                previous_status=previous,
                new_status=RequestStatus.RESOLVED,
                action="Solicitud resuelta",
                notes=(
                    f"Solución aplicada: {solution}\n"
                    f"Tiempo efectivo de resolución: {request.resolution_minutes} min.\n"
                    "Se solicita al solicitante confirmar la solución."
                ),
            )
        )
        return await self._confirmar_con_aviso(request_id, EventoAviso.SOLICITUD_RESUELTA, corte)

    async def confirmar(
        self,
        request_id: uuid.UUID,
        author_id: uuid.UUID,
        notes: str | None = None,
        ahora: datetime | None = None,
    ) -> Request:
        """Confirma una solicitud resuelta y la cierra.

        El solicitante (o un usuario con rol adecuado) valida que la solución
        aplicada es satisfactoria. La solicitud pasa a «Cerrada».
        """
        request = await self._load(request_id)
        if request.status != RequestStatus.RESOLVED:
            raise EstadoInvalidoError(
                f"una solicitud en estado {request.status} no puede confirmarse"
            )
        corte = ahora or _ahora()
        previous = request.status
        request.status = RequestStatus.CLOSED
        request.closed_at = corte
        request.logs.append(
            RequestLog(
                author_id=author_id,
                previous_status=previous,
                new_status=RequestStatus.CLOSED,
                action="Solicitud confirmada",
                notes=notes,
            )
        )
        return await self._confirmar_con_aviso(request_id, EventoAviso.SOLICITUD_CERRADA, corte)

    async def listar_bitacora(self, request_id: uuid.UUID) -> list[RequestLog]:
        """Entradas de la bitácora de una solicitud, de la más antigua a la más reciente."""
        if await self._session.get(Request, request_id) is None:
            raise SolicitudNoEncontradaError(f"request {request_id} does not exist")
        result = await self._session.scalars(
            select(RequestLog)
            .where(RequestLog.request_id == request_id)
            .order_by(RequestLog.created_at)
        )
        return list(result)
