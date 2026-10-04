"""HTTP endpoints for service requests (HU-01.1)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories.solicitud_repository import SolicitudRepository
from app.schemas.request import RequestCreate, RequestRead
from app.services.solicitud_service import SolicitudService, SolicitudValidationError

router = APIRouter(prefix="/solicitudes", tags=["solicitudes"])


def get_solicitud_service(
    session: AsyncSession = Depends(get_session),
) -> SolicitudService:
    return SolicitudService(SolicitudRepository(session), session)


@router.post("", response_model=RequestRead, status_code=status.HTTP_201_CREATED)
async def create_request(
    payload: RequestCreate,
    service: SolicitudService = Depends(get_solicitud_service),
) -> RequestRead:
    try:
        result = await service.create_request(payload)
        return RequestRead.model_validate(result)
    except SolicitudValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
