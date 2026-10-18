"""HTTP endpoints for service requests (HU-01.1, HU-01.3)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_permission
from app.core.permissions import Permission
from app.db.session import get_session
from app.models.identity import User
from app.repositories.solicitud_repository import SolicitudRepository
from app.schemas.request import (
    RequestAssistedCreate,
    RequestCreate,
    RequestRead,
    RequestWaitCreate,
)
from app.services.sla_clock_service import (
    EstadoInvalidoError,
    SlaClockService,
    SolicitudNoEncontradaError,
)
from app.services.solicitud_service import SolicitudService, SolicitudValidationError

router = APIRouter(prefix="/solicitudes", tags=["solicitudes"])


def get_solicitud_service(
    session: AsyncSession = Depends(get_session),
) -> SolicitudService:
    return SolicitudService(SolicitudRepository(session), session)


def get_sla_clock_service(
    session: AsyncSession = Depends(get_session),
) -> SlaClockService:
    return SlaClockService(session)


@router.post("", response_model=RequestRead, status_code=status.HTTP_201_CREATED)
async def create_request(
    payload: RequestCreate,
    _current_user: User = Depends(get_current_user),
    service: SolicitudService = Depends(get_solicitud_service),
) -> RequestRead:
    try:
        result = await service.create_request(payload)
        return RequestRead.model_validate(result)
    except SolicitudValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/asistido", response_model=RequestRead, status_code=status.HTTP_201_CREATED)
async def create_assisted_request(
    payload: RequestAssistedCreate,
    technician: User = Depends(require_permission(Permission.REQUESTS_CREATE_ASSISTED)),
    service: SolicitudService = Depends(get_solicitud_service),
) -> RequestRead:
    try:
        result = await service.create_assisted_request(payload, registered_by_id=technician.id)
        return RequestRead.model_validate(result)
    except SolicitudValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/{request_id}/espera", response_model=RequestRead)
async def put_request_on_hold(
    request_id: uuid.UUID,
    payload: RequestWaitCreate,
    technician: User = Depends(require_permission(Permission.REQUESTS_UPDATE)),
    service: SlaClockService = Depends(get_sla_clock_service),
) -> RequestRead:
    try:
        result = await service.suspender(request_id, technician.id, payload.reason, payload.detail)
    except SolicitudNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EstadoInvalidoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RequestRead.model_validate(result)


@router.post("/{request_id}/reanudar", response_model=RequestRead)
async def resume_request(
    request_id: uuid.UUID,
    technician: User = Depends(require_permission(Permission.REQUESTS_UPDATE)),
    service: SlaClockService = Depends(get_sla_clock_service),
) -> RequestRead:
    try:
        result = await service.reanudar(request_id, technician.id)
    except SolicitudNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EstadoInvalidoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RequestRead.model_validate(result)
