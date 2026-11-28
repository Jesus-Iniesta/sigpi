"""Asignación de técnicos a solicitudes (S5-03: HU-03.1, HU-03.3 y avisos de HU-07.1).

* `proponer` puntúa a los técnicos activos con las reglas de `domain/asignacion.py`.
* `asignar` cierra la asignación vigente, crea la nueva, pasa la solicitud a «Asignada»
  si estaba «Registrada» o «Clasificada», escribe la bitácora y avisa
  `request_assigned` al solicitante y al técnico, todo en una transacción.
* `asignar_automaticamente` toma al mejor candidato con capacidad: en P1 se ignora la carga
  máxima (S5-14); en las demás, los técnicos en su tope se descartan y, si no queda
  ninguno, la solicitud espera en la cola general (sin técnico, estado sin cambios).
  Si no hay candidatos y la solicitud es P1, avisa `p1_unassigned` a los jefes de servicio.

El turno se compara con la hora del centro de México (UTC-6).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.logging import get_logger, log_event
from app.domain import asignacion as reglas
from app.domain.asignacion import Propuesta, TecnicoCandidato
from app.domain.eventos import EventoAviso
from app.models.enums import Priority, RequestStatus, UserType
from app.models.identity import User
from app.models.request import Request, RequestAssignment, RequestLog
from app.repositories.asignacion_repository import AsignacionRepository
from app.services.notificacion_service import NotificacionService
from app.services.sla_clock_service import EstadoInvalidoError, SolicitudNoEncontradaError
from app.services.sla_service import as_utc

logger = get_logger("asignaciones")

# Misma hora que el contrato del acuerdo de servicio (`contrato_sla_service`).
HORA_CENTRO_MEXICO = timezone(timedelta(hours=-6), "UTC-6")


class TecnicoNoEncontradoError(NotFoundError):
    code = "technician_not_found"
    default_message = "El técnico indicado no existe."


class TecnicoNoDisponibleError(BusinessRuleError):
    code = "technician_unavailable"
    default_message = "El técnico indicado está inactivo o no es técnico."


@dataclass(frozen=True, slots=True)
class Asignado:
    """Asignación recién creada y el estatus con el que quedó la solicitud."""

    asignacion: RequestAssignment
    estado: RequestStatus


def _ahora() -> datetime:
    return datetime.now(UTC)


def _minuto_local(ahora: datetime) -> int:
    local = as_utc(ahora).astimezone(HORA_CENTRO_MEXICO)
    return local.hour * 60 + local.minute


def _candidato(tecnico: User, carga: dict[uuid.UUID, int]) -> TecnicoCandidato:
    turno = tecnico.shift if tecnico.shift is not None and tecnico.shift.is_active else None
    return TecnicoCandidato(
        id=tecnico.id,
        nombre=tecnico.full_name,
        activo=tecnico.is_active,
        categorias=frozenset(e.category_id for e in tecnico.specialties if e.is_active),
        turno=turno.name if turno is not None else None,
        turno_inicio=turno.start_minute if turno is not None else None,
        turno_fin=turno.end_minute if turno is not None else None,
        carga=carga.get(tecnico.id, 0),
        carga_maxima=tecnico.max_load,
    )


class AsignacionService:
    def __init__(
        self, session: AsyncSession, notificaciones: NotificacionService | None = None
    ) -> None:
        self._session = session
        self._repository = AsignacionRepository(session)
        self._notificaciones = notificaciones or NotificacionService(session)

    async def _solicitud(self, request_id: uuid.UUID) -> Request:
        request = await self._repository.get_request(request_id)
        if request is None:
            raise SolicitudNoEncontradaError(f"La solicitud {request_id} no existe.")
        return request

    async def _propuesta(self, request: Request, ahora: datetime) -> list[Propuesta]:
        tecnicos = await self._repository.list_technicians()
        carga = await self._repository.active_load()
        candidatos = [_candidato(t, carga) for t in tecnicos]
        return reglas.proponer(candidatos, request.category_id, _minuto_local(ahora))

    async def vigente(self, request_id: uuid.UUID) -> RequestAssignment | None:
        """Asignación vigente de la solicitud o `None` si aún no tiene técnico (S5-12)."""
        await self._solicitud(request_id)
        return await self._repository.get_vigente(request_id)

    async def proponer(
        self, request_id: uuid.UUID, ahora: datetime | None = None
    ) -> list[Propuesta]:
        """Técnicos candidatos del mejor al peor, con su puntaje y su desglose."""
        request = await self._solicitud(request_id)
        return await self._propuesta(request, ahora or _ahora())

    async def asignar(
        self,
        request_id: uuid.UUID,
        technician_id: uuid.UUID,
        actor_id: uuid.UUID,
        ahora: datetime | None = None,
    ) -> Asignado:
        """Asignación manual (`is_automatic=False`) del técnico elegido."""
        corte = ahora or _ahora()
        request = await self._solicitud(request_id)
        self._validar_estado(request)
        tecnico = await self._repository.get_user(technician_id)
        if tecnico is None:
            raise TecnicoNoEncontradoError()
        if not tecnico.is_active or tecnico.user_type != UserType.TECHNICAL:
            raise TecnicoNoDisponibleError()
        propuesta = next(
            (p for p in await self._propuesta(request, corte) if p.technician_id == technician_id),
            None,
        )
        return await self._guardar(
            request, technician_id, propuesta, actor_id, automatica=False, corte=corte
        )

    async def asignar_automaticamente(
        self,
        request_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        ahora: datetime | None = None,
    ) -> Asignado | None:
        """Asigna al primero de la propuesta (`is_automatic=True`).

        Sin candidatos devuelve `None` y la solicitud queda como estaba; si además es P1,
        avisa `p1_unassigned` a los jefes de servicio.
        """
        corte = ahora or _ahora()
        request = await self._solicitud(request_id)
        self._validar_estado(request)
        es_p1 = request.priority == Priority.P1
        propuesta = reglas.con_capacidad(await self._propuesta(request, corte), es_p1)
        if not propuesta:
            if es_p1:
                try:
                    await self._notificaciones.emitir(
                        EventoAviso.P1_SIN_ASIGNAR, request.id, ahora=corte
                    )
                    await self._session.commit()
                except Exception:
                    await self._session.rollback()
                    raise
            # Sin candidatos (o todos en su carga máxima y no es P1): queda en la cola
            # general, es decir, sin técnico y con el estado que ya tenía.
            log_event(logger, "asignacion_en_cola_general", folio=request.folio, p1=es_p1)
            return None
        mejor = propuesta[0]
        return await self._guardar(
            request,
            mejor.technician_id,
            mejor,
            actor_id or mejor.technician_id,
            automatica=True,
            corte=corte,
        )

    @staticmethod
    def _validar_estado(request: Request) -> None:
        if not reglas.puede_asignarse(request.status):
            raise EstadoInvalidoError(
                f"Una solicitud en estado {request.status} no admite asignación."
            )

    async def _guardar(
        self,
        request: Request,
        technician_id: uuid.UUID,
        propuesta: Propuesta | None,
        actor_id: uuid.UUID,
        *,
        automatica: bool,
        corte: datetime,
    ) -> Asignado:
        """Cierra la asignación vigente, crea la nueva, escribe la bitácora, avisa y confirma."""
        previo: RequestStatus = request.status
        nuevo = reglas.estado_al_asignar(previo)
        try:
            await self._repository.close_current(request.id, corte)
            asignacion = await self._repository.add(
                RequestAssignment(
                    request_id=request.id,
                    technician_id=technician_id,
                    score=float(propuesta.score) if propuesta is not None else None,
                    score_breakdown=propuesta.score_breakdown if propuesta is not None else None,
                    is_automatic=automatica,
                    assigned_at=corte,
                )
            )
            request.status = nuevo
            tecnico = await self._repository.get_user(technician_id)
            nombre = tecnico.full_name if tecnico is not None else str(technician_id)
            self._session.add(
                RequestLog(
                    request_id=request.id,
                    author_id=actor_id,
                    previous_status=previo,
                    new_status=nuevo,
                    action="Asignación automática" if automatica else "Técnico asignado",
                    notes=f"Asignada a {nombre}."
                    + (f" Puntaje: {propuesta.score_breakdown}." if propuesta else ""),
                )
            )
            await self._session.flush()
            await self._notificaciones.emitir(
                EventoAviso.SOLICITUD_ASIGNADA, request.id, ahora=corte
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        log_event(
            logger,
            "solicitud_asignada",
            folio=request.folio,
            automatica=automatica,
            score=propuesta.score if propuesta is not None else None,
        )
        return Asignado(asignacion=asignacion, estado=nuevo)
