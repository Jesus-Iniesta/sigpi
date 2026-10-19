"""Use cases for registering service requests (HU-01.1, HU-01.3)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.directory import DirectoryClient
from app.domain.estados import estado_inicial
from app.models.catalog import Categoria
from app.models.enums import RequestChannel
from app.models.identity import User
from app.models.request import Request, RequestLog
from app.repositories.solicitud_repository import SolicitudRepository
from app.schemas.request import RequestAssistedCreate, RequestCreate
from app.services.prioridad_service import PrioridadInvalidaError, PrioridadService

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
    ) -> None:
        self._repository = repository
        self._session = session
        self._prioridad = prioridad or PrioridadService()
        self._directory = directory

    async def create_request(self, payload: RequestCreate) -> Request:
        return await self._register(payload)

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
        return await self._register(payload, log)

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
        return await self._repository.add(request)

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
