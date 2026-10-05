import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.identity import User
from app.models.organization import OrganizationalUnit
from app.repositories.catalog_repository import (
    CategoryRepository,
    ServiceAreaRepository,
    ShiftRepository,
    SpecialtyRepository,
    TechnicianRepository,
)
from app.schemas.catalog import (
    CategoryCreate,
    CategoryRead,
    OrganizationalUnitRead,
    ServiceAreaCreate,
    ServiceAreaRead,
    ShiftCreate,
    ShiftRead,
    SpecialtyCreate,
    SpecialtyRead,
    TechnicianProfileUpdate,
    TechnicianRead,
)
from app.services.catalog_service import CatalogService, CatalogValidationError

router = APIRouter(prefix="/catalog", tags=["catalog"])


def get_catalog_service(session: AsyncSession = Depends(get_session)) -> CatalogService:
    return CatalogService(
        areas=ServiceAreaRepository(session),
        categories=CategoryRepository(session),
        specialties=SpecialtyRepository(session),
        shifts=ShiftRepository(session),
        technicians=TechnicianRepository(session),
    )


def _to_technician_read(user: User) -> TechnicianRead:
    return TechnicianRead(
        id=user.id,
        full_name=user.full_name,
        support_level=user.support_level,
        shift_id=user.shift_id,
        max_load=user.max_load,
        is_active=user.is_active,
        specialty_ids=[specialty.id for specialty in user.specialties],
    )


def _unprocessable(exc: CatalogValidationError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/areas", response_model=list[ServiceAreaRead])
async def list_areas(service: CatalogService = Depends(get_catalog_service)):
    return await service.list_areas()


@router.get("/organizational-units", response_model=list[OrganizationalUnitRead])
async def list_organizational_units(
    session: AsyncSession = Depends(get_session),
):
    result = await session.scalars(
        select(OrganizationalUnit)
        .where(OrganizationalUnit.is_active.is_(True))
        .order_by(OrganizationalUnit.name)
    )
    return list(result)


@router.post("/areas", response_model=ServiceAreaRead, status_code=status.HTTP_201_CREATED)
async def create_area(
    payload: ServiceAreaCreate, service: CatalogService = Depends(get_catalog_service)
):
    return await service.create_area(payload)


@router.get("/categories", response_model=list[CategoryRead])
async def list_categories(
    area_id: uuid.UUID | None = None, service: CatalogService = Depends(get_catalog_service)
):
    return await service.list_categories(area_id=area_id)


@router.post("/categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate, service: CatalogService = Depends(get_catalog_service)
):
    try:
        return await service.create_category(payload)
    except CatalogValidationError as exc:
        raise _unprocessable(exc) from exc


@router.get("/specialties", response_model=list[SpecialtyRead])
async def list_specialties(
    category_id: uuid.UUID | None = None, service: CatalogService = Depends(get_catalog_service)
):
    return await service.list_specialties(category_id=category_id)


@router.post("/specialties", response_model=SpecialtyRead, status_code=status.HTTP_201_CREATED)
async def create_specialty(
    payload: SpecialtyCreate, service: CatalogService = Depends(get_catalog_service)
):
    try:
        return await service.create_specialty(payload)
    except CatalogValidationError as exc:
        raise _unprocessable(exc) from exc


@router.get("/shifts", response_model=list[ShiftRead])
async def list_shifts(service: CatalogService = Depends(get_catalog_service)):
    return await service.list_shifts()


@router.post("/shifts", response_model=ShiftRead, status_code=status.HTTP_201_CREATED)
async def create_shift(
    payload: ShiftCreate, service: CatalogService = Depends(get_catalog_service)
):
    try:
        return await service.create_shift(payload)
    except CatalogValidationError as exc:
        raise _unprocessable(exc) from exc


@router.get("/technicians", response_model=list[TechnicianRead])
async def list_technicians(
    specialty_id: uuid.UUID | None = None,
    service: CatalogService = Depends(get_catalog_service),
):
    technicians = await service.list_technicians(specialty_id=specialty_id)
    return [_to_technician_read(t) for t in technicians]


@router.patch("/technicians/{user_id}", response_model=TechnicianRead)
async def update_technician(
    user_id: uuid.UUID,
    payload: TechnicianProfileUpdate,
    service: CatalogService = Depends(get_catalog_service),
):
    try:
        technician = await service.update_technician_profile(user_id, payload)
    except CatalogValidationError as exc:
        raise _unprocessable(exc) from exc
    return _to_technician_read(technician)
