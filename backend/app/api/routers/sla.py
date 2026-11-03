import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.enums import Priority
from app.repositories.sla_repository import SlaRepository
from app.schemas.sla import (
    EffectiveSlaRead,
    SlaAgreementCreate,
    SlaAgreementRead,
    SlaOptionsRead,
    SlaVersionCreate,
    SlaVersionRead,
)
from app.services.sla_service import SlaService

# Los errores esperados del servicio son subclases de `SigpiError`; el manejador global
# los convierte en la respuesta HTTP correspondiente (404, 409 o 422).
router = APIRouter(prefix="/sla", tags=["sla"])


def get_sla_service(session: AsyncSession = Depends(get_session)) -> SlaService:
    return SlaService(SlaRepository(session))


@router.get("/options", response_model=SlaOptionsRead)
async def list_options():
    default_name, service_types = SlaService.list_options()
    return SlaOptionsRead(default_name=default_name, service_types=service_types)


@router.get("/agreements", response_model=list[SlaAgreementRead])
async def list_agreements(service: SlaService = Depends(get_sla_service)):
    return await service.list_agreements()


@router.post("/agreements", response_model=SlaAgreementRead, status_code=status.HTTP_201_CREATED)
async def create_agreement(
    payload: SlaAgreementCreate, service: SlaService = Depends(get_sla_service)
):
    return await service.create_agreement(payload)


@router.get("/agreements/{agreement_id}/versions", response_model=list[SlaVersionRead])
async def list_versions(
    agreement_id: uuid.UUID,
    priority: Priority | None = None,
    service: SlaService = Depends(get_sla_service),
):
    return await service.list_versions(agreement_id, priority=priority)


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
    return await service.publish_version(agreement_id, payload)


@router.get("/effective", response_model=EffectiveSlaRead)
async def get_effective_sla(
    priority: Priority,
    category_id: uuid.UUID | None = None,
    at: datetime | None = None,
    service: SlaService = Depends(get_sla_service),
):
    return await service.resolve_effective(category_id, priority, at)
