"""HTTP endpoints de seguimiento y resolución de solicitudes (HU-04.1)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.core.permissions import Permission
from app.db.session import get_session
from app.models.identity import User
from app.schemas.request import (
    RequestConfirmCreate,
    RequestDiagnosisCreate,
    RequestLogRead,
    RequestRead,
    RequestResolveCreate,
)
from app.services.seguimiento_service import SeguimientoService
from app.services.sla_clock_service import EstadoInvalidoError, SolicitudNoEncontradaError

router = APIRouter(prefix="/solicitudes", tags=["seguimiento"])


def get_seguimiento_service(
    session: AsyncSession = Depends(get_session),
) -> SeguimientoService:
    return SeguimientoService(session)


@router.post("/{request_id}/diagnostico", response_model=RequestRead)
async def register_diagnosis(
    request_id: uuid.UUID,
    payload: RequestDiagnosisCreate,
    technician: User = Depends(require_permission(Permission.REQUESTS_UPDATE)),
    service: SeguimientoService = Depends(get_seguimiento_service),
) -> RequestRead:
    try:
        result = await service.registrar_diagnostico(request_id, technician.id, payload.diagnosis)
    except SolicitudNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EstadoInvalidoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RequestRead.model_validate(result)


@router.post("/{request_id}/iniciar", response_model=RequestRead)
async def start_request(
    request_id: uuid.UUID,
    technician: User = Depends(require_permission(Permission.REQUESTS_UPDATE)),
    service: SeguimientoService = Depends(get_seguimiento_service),
) -> RequestRead:
    try:
        result = await service.iniciar_atencion(request_id, technician.id)
    except SolicitudNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EstadoInvalidoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RequestRead.model_validate(result)


@router.post("/{request_id}/resolver", response_model=RequestRead)
async def resolve_request(
    request_id: uuid.UUID,
    payload: RequestResolveCreate,
    technician: User = Depends(require_permission(Permission.REQUESTS_RESOLVE)),
    service: SeguimientoService = Depends(get_seguimiento_service),
) -> RequestRead:
    try:
        result = await service.resolver(
            request_id, technician.id, payload.solution, diagnosis=payload.diagnosis
        )
    except SolicitudNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EstadoInvalidoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RequestRead.model_validate(result)


@router.post("/{request_id}/confirmar", response_model=RequestRead)
async def confirm_request(
    request_id: uuid.UUID,
    payload: RequestConfirmCreate,
    technician: User = Depends(require_permission(Permission.REQUESTS_CLOSE)),
    service: SeguimientoService = Depends(get_seguimiento_service),
) -> RequestRead:
    try:
        result = await service.confirmar(request_id, technician.id, payload.notes)
    except SolicitudNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EstadoInvalidoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RequestRead.model_validate(result)


@router.get("/{request_id}/bitacora", response_model=list[RequestLogRead])
async def list_request_log(
    request_id: uuid.UUID,
    _technician: User = Depends(require_permission(Permission.REQUESTS_UPDATE)),
    service: SeguimientoService = Depends(get_seguimiento_service),
) -> list[RequestLogRead]:
    try:
        entries = await service.listar_bitacora(request_id)
    except SolicitudNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [RequestLogRead.model_validate(entry) for entry in entries]
