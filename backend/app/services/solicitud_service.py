"""Use cases for registering service requests (HU-01.1, HU-01.3) and their automatic
classification at registration time (HU-02.1, S4-13).

Al fijar la prioridad se asigna la versión vigente del acuerdo de nivel de servicio; el
resultado, el estatus y la versión se confirman en una sola transacción (regla 7).

El alta avisa al solicitante con `request_registered` (S4-07, HU-07.1) en la misma
transacción, ya con la categoría, la prioridad y la fecha compromiso que deja la
clasificación. Si la escritura del aviso falla, la solicitud no se registra."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, log_event
from app.domain.directory import DirectoryClient
from app.domain.estados import estado_inicial
from app.domain.eventos import EventoAviso
from app.models.catalog import Categoria
from app.models.classification import ClassificationResult, ModelVersion
from app.models.enums import RequestChannel, RequestStatus
from app.models.identity import User
from app.models.request import Request, RequestLog
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.revision_repository import RevisionRepository
from app.repositories.sla_repository import SlaRepository
from app.repositories.solicitud_repository import SolicitudRepository
from app.schemas.request import RequestAssistedCreate, RequestCreate
from app.services.auditoria_service import AuditoriaService
from app.services.clasificacion_service import ClasificacionService
from app.services.notificacion_service import NotificacionService
from app.services.prioridad_service import PrioridadInvalidaError, PrioridadService
from app.services.revision_service import decidir_estatus
from app.services.sla_service import SlaService

logger = get_logger("solicitudes")

ACCION_CLASIFICACION = "Clasificación automática"

_CHANNEL_LABELS = {
    RequestChannel.PHONE: "por teléfono",
    RequestChannel.IN_PERSON: "de forma presencial",
}


class SolicitudValidationError(ValueError):
    """Raised when a request cannot be registered with the supplied references."""


class SolicitudService:
    def __init__(
        self,
        repository: SolicitudRepository,
        session: AsyncSession,
        prioridad: PrioridadService | None = None,
        directory: DirectoryClient | None = None,
        clasificacion: ClasificacionService | None = None,
        sla: SlaService | None = None,
        notificaciones: NotificacionService | None = None,
    ) -> None:
        self._repository = repository
        self._session = session
        self._prioridad = prioridad or PrioridadService()
        self._directory = directory
        # Sin servicio de clasificación, el alta solo registra (comportamiento previo a S4-13).
        self._clasificacion = clasificacion
        self._sla = sla or SlaService(
            SlaRepository(session), AuditoriaService(AuditoriaRepository(session))
        )
        self._notificaciones = notificaciones or NotificacionService(session)

    async def create_request(
        self, payload: RequestCreate, registered_by_id: uuid.UUID | None = None
    ) -> Request:
        request = await self._register(payload)
        await self._clasificar(request, registered_by_id, conservar_niveles=False)
        return await self._confirmar_alta(request)

    async def create_assisted_request(
        self, payload: RequestAssistedCreate, registered_by_id: uuid.UUID
    ) -> Request:
        """Register a request received by phone or in person on behalf of a requester.

        The technician who captures it is stored as the author of the first bitácora
        entry, so the request and its origin are saved in a single transaction.
        """
        log = RequestLog(
            author_id=registered_by_id,
            previous_status=None,
            action=f"Solicitud registrada {_CHANNEL_LABELS[payload.channel]}",
            notes="Registro asistido: el técnico capturó la solicitud en nombre del solicitante.",
        )
        request = await self._register(payload, log)
        await self._clasificar(request, registered_by_id, conservar_niveles=True)
        return await self._confirmar_alta(request)

    async def _confirmar_alta(self, request: Request) -> Request:
        """Guarda el aviso de alta y confirma la solicitud, su clasificación y el aviso."""
        try:
            await self._notificaciones.emitir(EventoAviso.SOLICITUD_REGISTRADA, request.id)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(request)
        return request

    async def ultima_clasificacion(self, request_id: uuid.UUID) -> ClassificationResult | None:
        """Último resultado de clasificación de la solicitud, con categoría y versión."""
        resultados = await RevisionRepository(self._session).ultimos_resultados([request_id])
        return resultados.get(request_id)

    async def _clasificar(
        self, request: Request, author_id: uuid.UUID | None, *, conservar_niveles: bool
    ) -> Request:
        """Clasifica la solicitud recién registrada y decide su estatus (HU-02.1, RN-06).

        * «Clasificada»: aplica categoría, urgencia e impacto, recalcula la prioridad y
          asigna la versión vigente del acuerdo de nivel de servicio.
        * «Por revisar»: guarda la confianza, pero no aplica la propuesta hasta la revisión.

        Con `conservar_niveles` (registro asistido) se respetan la urgencia y el impacto que
        capturó el técnico; el clasificador solo completa los que falten. Si el clasificador
        falla, la solicitud queda «Registrada» y el alta no falla. El resultado, el estatus
        y la versión se escriben en un punto de guardado: si algo falla, no queda ninguno.
        No confirma: el alta se confirma completa en `_confirmar_alta`.
        """
        if self._clasificacion is None or request.status != RequestStatus.REGISTERED:
            return request
        author_id = author_id or request.requester_id
        try:
            async with self._session.begin_nested():
                await self._aplicar_clasificacion(request, author_id, conservar_niveles)
        except Exception as exc:  # noqa: BLE001 — el alta nunca falla por el clasificador
            await self._session.refresh(request)
            log_event(
                logger,
                "clasificacion_fallida",
                level="ERROR",
                folio=request.folio,
                error=type(exc).__name__,
                detalle=str(exc),
            )
        return request

    async def _aplicar_clasificacion(
        self, request: Request, author_id: uuid.UUID, conservar_niveles: bool
    ) -> None:
        resultado = await self._clasificacion.clasificar(request, confirmar=False)
        estatus = decidir_estatus(resultado)
        request.classification_confidence = float(resultado.confidence)
        if estatus == RequestStatus.CLASSIFIED:
            if resultado.category_id is not None:
                request.category_id = resultado.category_id
            if not conservar_niveles or request.urgency is None:
                request.urgency = resultado.urgency
            if not conservar_niveles or request.impact is None:
                request.impact = resultado.impact
            self._prioridad.aplicar(request)
        self._session.add(
            RequestLog(
                request_id=request.id,
                author_id=author_id,
                previous_status=request.status,
                new_status=estatus,
                action=ACCION_CLASIFICACION,
                notes=_nota_clasificacion(
                    float(resultado.confidence), await self._version(resultado), estatus
                ),
            )
        )
        request.status = estatus
        if estatus == RequestStatus.CLASSIFIED:
            await self._sla.asignar_version_vigente(request, author_id)

    async def _version(self, resultado: ClassificationResult) -> str:
        """Versión del modelo del resultado; `session.get` la toma del mapa de identidad."""
        if resultado.model_version_id is None:
            return "desconocida"
        model_version = await self._session.get(ModelVersion, resultado.model_version_id)
        return model_version.version if model_version is not None else "desconocida"

    async def _register(self, payload: RequestCreate, log: RequestLog | None = None) -> Request:
        requester = await self._find_requester(payload)

        if payload.category_id is not None:
            category = await self._session.get(Categoria, payload.category_id)
            if category is None or not category.is_active:
                raise SolicitudValidationError(
                    f"category {payload.category_id} does not exist or is inactive"
                )

        if payload.related_request_id is not None:
            related = await self._session.get(Request, payload.related_request_id)
            if related is None:
                raise SolicitudValidationError(
                    f"related request {payload.related_request_id} does not exist"
                )

        request = Request(
            requester_id=requester.id if requester is not None else None,
            requester_institutional_id=payload.requester_institutional_id,
            category_id=payload.category_id,
            asset_id=payload.asset_id,
            related_request_id=payload.related_request_id,
            folio=await self._repository.next_folio(),
            title=payload.title,
            description=payload.description,
            physical_location=payload.physical_location,
            channel=payload.channel,
            status=estado_inicial(requester is not None),
            urgency=payload.urgency,
            impact=payload.impact,
        )
        try:
            self._prioridad.aplicar(request)
        except PrioridadInvalidaError as exc:
            raise SolicitudValidationError(str(exc)) from exc
        if log is not None:
            log.new_status = request.status
            if requester is None and payload.requester_institutional_id is not None:
                note = await self._unverified_note(payload.requester_institutional_id)
                log.notes = f"{log.notes} {note}"
            request.logs.append(log)
        # Sin confirmar: el alta se confirma completa, con su clasificación y su aviso.
        self._session.add(request)
        await self._session.flush()
        return request

    async def _find_requester(self, payload: RequestCreate) -> User | None:
        """Return the requester's account, or None when they cannot be located yet.

        Locating no one is not an error: the request is still registered, marked as
        pending verification. An existing but inactive account is rejected.
        """
        if payload.requester_id is not None:
            requester = await self._session.get(User, payload.requester_id)
            if requester is None or not requester.is_active:
                raise SolicitudValidationError(
                    f"requester {payload.requester_id} does not exist or is inactive"
                )
            return requester

        result = await self._session.execute(
            select(User).where(User.institutional_id == payload.requester_institutional_id)
        )
        requester = result.scalar_one_or_none()
        if requester is not None and not requester.is_active:
            raise SolicitudValidationError(
                f"requester {payload.requester_institutional_id} is inactive"
            )
        return requester

    async def _unverified_note(self, institutional_id: str) -> str:
        """Explain in the bitácora why the requester was left pending verification."""
        profile = None
        if self._directory is not None:
            profile = await self._directory.fetch_profile(institutional_id)
        if profile is not None:
            detail = "el directorio lo reconoce, pero aún no tiene cuenta en SIGPI"
        else:
            detail = "no aparece en el directorio"
        return f"Solicitante «{institutional_id}» por verificar: {detail}."


def _nota_clasificacion(confianza: float, version: str, estatus: RequestStatus) -> str:
    if estatus == RequestStatus.CLASSIFIED:
        decision = "se aplicó la clasificación propuesta"
    else:
        decision = "la confianza es baja: queda por revisar y no se aplica la categoría"
    return f"Confianza {confianza:.0%}, modelo {version}: {decision}."
