import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.enums import Priority
from app.repositories.sla_repository import SlaRepository
from app.schemas.sla import (
    EffectiveSlaRead,
    SlaAgreementCreate,
    SlaAgreementRead,
    SlaVersionCreate,
    SlaVersionRead,
)
from app.services.sla_service import (
    SlaConflictError,
    SlaNotConfiguredError,
    SlaNotFoundError,
    SlaService,
    SlaValidationError,
)

router = APIRouter(prefix="/sla", tags=["sla"])


def get_sla_service(session: AsyncSession = Depends(get_session)) -> SlaService:
    return SlaService(SlaRepository(session))


@router.get("/agreements", response_model=list[SlaAgreementRead])
async def list_agreements(service: SlaService = Depends(get_sla_service)):
    return await service.list_agreements()


@router.post("/agreements", response_model=SlaAgreementRead, status_code=status.HTTP_201_CREATED)
async def create_agreement(
    payload: SlaAgreementCreate, service: SlaService = Depends(get_sla_service)
):
    try:
        return await service.create_agreement(payload)
    except SlaConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except SlaValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/agreements/{agreement_id}/versions", response_model=list[SlaVersionRead])
async def list_versions(
    agreement_id: uuid.UUID,
    priority: Priority | None = None,
    service: SlaService = Depends(get_sla_service),
):
    try:
        return await service.list_versions(agreement_id, priority=priority)
    except SlaNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post(
    "/agreements/{agreement_id}/versions",
    response_model=list[SlaVersionRead],
    status_code=status.HTTP_201_CREATED,
)
async def publish_version(
    agreement_id: uuid.UUID,
    payload: SlaVersionCreate,
    service: SlaService = Depends(get_sla_service),
):
    try:
        return await service.publish_version(agreement_id, payload)
    except SlaNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except SlaValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/effective", response_model=EffectiveSlaRead)
async def get_effective_sla(
    priority: Priority,
    category_id: uuid.UUID | None = None,
    at: datetime | None = None,
    service: SlaService = Depends(get_sla_service),
):
    try:
        return await service.resolve_effective(category_id, priority, at)
    except SlaNotConfiguredError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
