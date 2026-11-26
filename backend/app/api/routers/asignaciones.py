"""Endpoints de la asignación de técnicos (S5-03, S5-12, HU-03.1): propuesta, asignación
y consulta de la asignación vigente."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.core.permissions import Permission
from app.db.session import get_session
from app.models.identity import User
from app.schemas.asignacion import (
    AsignacionCreate,
    AsignacionRead,
    AsignacionVigenteRead,
    CandidatoRead,
)
from app.services.asignacion_service import AsignacionService
from app.services.sla_clock_service import EstadoInvalidoError, SolicitudNoEncontradaError

router = APIRouter(prefix="/asignaciones", tags=["asignaciones"])


def get_asignacion_service(session: AsyncSession = Depends(get_session)) -> AsignacionService:
    return AsignacionService(session)


@router.get("/{request_id}", response_model=AsignacionVigenteRead | None)
async def consultar_asignacion_vigente(
    request_id: uuid.UUID,
    _user: User = Depends(require_permission(Permission.REQUESTS_ASSIGN)),
    service: AsignacionService = Depends(get_asignacion_service),
) -> AsignacionVigenteRead | None:
    """Técnico asignado y desglose de su puntaje; `null` si la solicitud no tiene técnico."""
    try:
        asignacion = await service.vigente(request_id)
    except SolicitudNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AsignacionVigenteRead.from_model(asignacion) if asignacion is not None else None


@router.get("/{request_id}/propuesta", response_model=list[CandidatoRead])
async def proponer_tecnicos(
    request_id: uuid.UUID,
    _user: User = Depends(require_permission(Permission.REQUESTS_ASSIGN)),
    service: AsignacionService = Depends(get_asignacion_service),
) -> list[CandidatoRead]:
    try:
        propuesta = await service.proponer(request_id)
    except SolicitudNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [CandidatoRead.from_propuesta(p) for p in propuesta]


@router.post("/{request_id}", response_model=AsignacionRead)
async def asignar_tecnico(
    request_id: uuid.UUID,
    payload: AsignacionCreate,
    user: User = Depends(require_permission(Permission.REQUESTS_ASSIGN)),
    service: AsignacionService = Depends(get_asignacion_service),
) -> AsignacionRead:
    try:
        asignado = await service.asignar(request_id, payload.technician_id, user.id)
    except SolicitudNoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EstadoInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return AsignacionRead.from_model(asignado)
