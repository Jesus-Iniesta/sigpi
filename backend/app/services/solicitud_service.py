"""Use cases for registering service requests (HU-01.1)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Categoria
from app.models.enums import RequestStatus
from app.models.identity import User
from app.models.request import Request
from app.repositories.solicitud_repository import SolicitudRepository
from app.schemas.request import RequestCreate


class SolicitudValidationError(ValueError):
    """Raised when a request cannot be registered with the supplied references."""


class SolicitudService:
    def __init__(self, repository: SolicitudRepository, session: AsyncSession) -> None:
        self._repository = repository
        self._session = session

    async def create_request(self, payload: RequestCreate) -> Request:
        requester = await self._session.get(User, payload.requester_id)
        if requester is None or not requester.is_active:
            raise SolicitudValidationError(
                f"requester {payload.requester_id} does not exist or is inactive"
            )

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
            requester_id=payload.requester_id,
            category_id=payload.category_id,
            asset_id=payload.asset_id,
            related_request_id=payload.related_request_id,
            folio=await self._repository.next_folio(),
            title=payload.title,
            description=payload.description,
            physical_location=payload.physical_location,
            channel=payload.channel,
            status=RequestStatus.REGISTERED,
            urgency=payload.urgency,
            impact=payload.impact,
        )
        return await self._repository.add(request)
