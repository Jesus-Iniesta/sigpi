import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.catalog import AreaServicio, Categoria, Especialidad, Turno
from app.schemas.catalog import (
    CategoryCreate,
    ServiceAreaCreate,
    ShiftCreate,
    SpecialtyCreate,
    TechnicianProfileUpdate,
)
from app.services.catalog_service import CatalogService, CatalogValidationError


class FakeRepo:
    """In-memory repository: stores objects by id, no database needed."""

    def __init__(self, items=None) -> None:
        self.items = {item.id: item for item in (items or [])}

    async def list_all(self, **_filters):
        return list(self.items.values())

    async def get(self, item_id):
        return self.items.get(item_id)

    async def get_many(self, ids):
        return [self.items[i] for i in ids if i in self.items]

    async def create(self, item):
        item.id = item.id or uuid.uuid4()
        self.items[item.id] = item
        return item

    async def save(self, item):
        self.items[item.id] = item
        return item


def _service(*, areas=None, categories=None, specialties=None, shifts=None, technicians=None):
    return CatalogService(
        areas=FakeRepo(areas),
        categories=FakeRepo(categories),
        specialties=FakeRepo(specialties),
        shifts=FakeRepo(shifts),
        technicians=FakeRepo(technicians),
    )


def _technician(**overrides):
    base = {
        "id": uuid.uuid4(),
        "full_name": "Técnico de prueba",
        "support_level": "level_1",
        "shift_id": None,
        "max_load": 4,
        "is_active": True,
        "specialties": [],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_create_area_persists_it() -> None:
    service = _service()
    area = await service.create_area(ServiceAreaCreate(unit_id=uuid.uuid4(), name="Redes"))
    assert area.name == "Redes"
    assert area in await service.list_areas()


@pytest.mark.asyncio
async def test_create_category_requires_existing_area() -> None:
    service = _service()
    with pytest.raises(CatalogValidationError):
        await service.create_category(CategoryCreate(area_id=uuid.uuid4(), name="Conmutación"))


@pytest.mark.asyncio
async def test_create_category_with_existing_area() -> None:
    area = AreaServicio(id=uuid.uuid4(), unit_id=uuid.uuid4(), name="Redes")
    service = _service(areas=[area])
    category = await service.create_category(CategoryCreate(area_id=area.id, name="Conmutación"))
    assert category.area_id == area.id


@pytest.mark.asyncio
async def test_create_specialty_requires_existing_category() -> None:
    service = _service()
    with pytest.raises(CatalogValidationError):
        await service.create_specialty(SpecialtyCreate(category_id=uuid.uuid4(), name="VLAN"))


@pytest.mark.asyncio
async def test_create_specialty_with_existing_category() -> None:
    category = Categoria(id=uuid.uuid4(), area_id=uuid.uuid4(), name="Redes")
    service = _service(categories=[category])
    specialty = await service.create_specialty(
        SpecialtyCreate(category_id=category.id, name="VLAN")
    )
    assert specialty.category_id == category.id


def test_shift_schema_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError):
        ShiftCreate(name="Inválido", start_minute=600, end_minute=480)


@pytest.mark.asyncio
async def test_create_shift_persists_it() -> None:
    service = _service()
    shift = await service.create_shift(
        ShiftCreate(name="Matutino", start_minute=420, end_minute=900)
    )
    assert shift.start_minute == 420
    assert shift in await service.list_shifts()


@pytest.mark.asyncio
async def test_update_technician_sets_specialties_rn08() -> None:
    specialty = Especialidad(id=uuid.uuid4(), category_id=uuid.uuid4(), name="VLAN")
    technician = _technician()
    service = _service(specialties=[specialty], technicians=[technician])

    updated = await service.update_technician_profile(
        technician.id, TechnicianProfileUpdate(specialty_ids=[specialty.id], max_load=6)
    )

    assert [s.id for s in updated.specialties] == [specialty.id]
    assert updated.max_load == 6


@pytest.mark.asyncio
async def test_update_technician_rejects_unknown_specialty() -> None:
    technician = _technician()
    service = _service(technicians=[technician])
    with pytest.raises(CatalogValidationError):
        await service.update_technician_profile(
            technician.id, TechnicianProfileUpdate(specialty_ids=[uuid.uuid4()])
        )


@pytest.mark.asyncio
async def test_update_technician_rejects_unknown_shift() -> None:
    technician = _technician()
    service = _service(technicians=[technician])
    with pytest.raises(CatalogValidationError):
        await service.update_technician_profile(
            technician.id, TechnicianProfileUpdate(shift_id=uuid.uuid4())
        )


@pytest.mark.asyncio
async def test_update_technician_applies_existing_shift() -> None:
    shift = Turno(id=uuid.uuid4(), name="Matutino", start_minute=420, end_minute=900)
    technician = _technician()
    service = _service(shifts=[shift], technicians=[technician])
    updated = await service.update_technician_profile(
        technician.id, TechnicianProfileUpdate(shift_id=shift.id)
    )
    assert updated.shift_id == shift.id


@pytest.mark.asyncio
async def test_update_unknown_technician_fails() -> None:
    service = _service()
    with pytest.raises(CatalogValidationError):
        await service.update_technician_profile(uuid.uuid4(), TechnicianProfileUpdate(max_load=5))


@pytest.mark.asyncio
async def test_partial_update_keeps_unspecified_fields() -> None:
    specialty = Especialidad(id=uuid.uuid4(), category_id=uuid.uuid4(), name="VLAN")
    technician = _technician(specialties=[specialty], max_load=4)
    service = _service(specialties=[specialty], technicians=[technician])
    updated = await service.update_technician_profile(
        technician.id, TechnicianProfileUpdate(max_load=8)
    )
    assert updated.max_load == 8
    assert updated.specialties == [specialty]
