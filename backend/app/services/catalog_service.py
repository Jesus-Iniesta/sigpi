"""Casos de uso del catálogo de técnicos y áreas de soporte (HU-11.1).

Reglas aplicadas:
- RN-08: un técnico solo puede recibir asignaciones de las especialidades que
  tiene habilitadas; este servicio es la única puerta para declararlas.
- Vigencia inmediata: no hay caché en esta capa; cada consulta llega a la base
  de datos, así que un cambio de turno o de carga máxima aplica en la siguiente
  asignación sin reiniciar el servicio.
"""

import uuid

from app.domain.catalog_options import (
    CATEGORY_OPTIONS,
    MAX_LOAD_MAX,
    MAX_LOAD_MIN,
    SERVICE_AREA_OPTIONS,
    SHIFT_OPTIONS,
    SPECIALTY_OPTIONS,
    CatalogOptionError,
    ensure_option,
    shift_option,
    specialties_for,
)
from app.models.catalog import AreaServicio, Categoria, Especialidad, Turno
from app.models.identity import User
from app.repositories.catalog_repository import (
    CategoryRepository,
    ServiceAreaRepository,
    ShiftRepository,
    SpecialtyRepository,
    TechnicianRepository,
)
from app.schemas.catalog import (
    CatalogOptionNotAllowedError,
    CatalogOptionsRead,
    CategoryCreate,
    MaxLoadRange,
    ServiceAreaCreate,
    ShiftCreate,
    ShiftOptionRead,
    SpecialtyCreate,
    SpecialtyOptionsRead,
    TechnicianProfileUpdate,
)


class CatalogValidationError(ValueError):
    """Raised when a catalog change references data that does not exist."""


class CatalogService:
    def __init__(
        self,
        areas: ServiceAreaRepository,
        categories: CategoryRepository,
        specialties: SpecialtyRepository,
        shifts: ShiftRepository,
        technicians: TechnicianRepository,
    ) -> None:
        self._areas = areas
        self._categories = categories
        self._specialties = specialties
        self._shifts = shifts
        self._technicians = technicians

    # --- opciones predefinidas (COR-04) ---------------------------------------
    @staticmethod
    def get_options() -> CatalogOptionsRead:
        """Listas cerradas que el frontend usa para llenar sus selectores."""
        return CatalogOptionsRead(
            service_areas=list(SERVICE_AREA_OPTIONS),
            categories=list(CATEGORY_OPTIONS),
            specialties=[
                SpecialtyOptionsRead(category=category, names=list(names))
                for category, names in SPECIALTY_OPTIONS.items()
            ],
            shifts=[
                ShiftOptionRead(
                    name=option.name,
                    start_minute=option.start_minute,
                    end_minute=option.end_minute,
                )
                for option in SHIFT_OPTIONS
            ],
            max_load=MaxLoadRange(min=MAX_LOAD_MIN, max=MAX_LOAD_MAX),
        )

    # --- áreas de servicio ---------------------------------------------------
    async def list_areas(self) -> list[AreaServicio]:
        return await self._areas.list_all()

    async def create_area(self, payload: ServiceAreaCreate) -> AreaServicio:
        area = AreaServicio(
            unit_id=payload.unit_id, name=payload.name, description=payload.description
        )
        return await self._areas.create(area)

    # --- categorías ------------------------------------------------------------
    async def list_categories(self, *, area_id: uuid.UUID | None = None) -> list[Categoria]:
        return await self._categories.list_all(area_id=area_id)

    async def create_category(self, payload: CategoryCreate) -> Categoria:
        if await self._areas.get(payload.area_id) is None:
            raise CatalogValidationError(f"service area {payload.area_id} does not exist")
        category = Categoria(
            area_id=payload.area_id, name=payload.name, description=payload.description
        )
        return await self._categories.create(category)

    # --- especialidades --------------------------------------------------------
    async def list_specialties(self, *, category_id: uuid.UUID | None = None) -> list[Especialidad]:
        return await self._specialties.list_all(category_id=category_id)

    async def create_specialty(self, payload: SpecialtyCreate) -> Especialidad:
        category = await self._categories.get(payload.category_id)
        if category is None:
            raise CatalogValidationError(f"category {payload.category_id} does not exist")
        try:
            ensure_option(
                f"las especialidades de la categoría «{category.name}»",
                payload.name,
                specialties_for(category.name),
            )
        except CatalogOptionError as exc:
            raise CatalogOptionNotAllowedError(str(exc)) from exc
        specialty = Especialidad(category_id=payload.category_id, name=payload.name)
        return await self._specialties.create(specialty)

    # --- turnos ----------------------------------------------------------------
    async def list_shifts(self) -> list[Turno]:
        return await self._shifts.list_all()

    async def create_shift(self, payload: ShiftCreate) -> Turno:
        # El horario no lo envía el cliente: se toma del turno predefinido.
        try:
            option = shift_option(payload.name)
        except CatalogOptionError as exc:
            raise CatalogOptionNotAllowedError(str(exc)) from exc
        shift = Turno(
            name=option.name, start_minute=option.start_minute, end_minute=option.end_minute
        )
        return await self._shifts.create(shift)

    # --- técnicos --------------------------------------------------------------
    async def list_technicians(self, *, specialty_id: uuid.UUID | None = None) -> list[User]:
        return await self._technicians.list_all(specialty_id=specialty_id)

    async def update_technician_profile(
        self, user_id: uuid.UUID, payload: TechnicianProfileUpdate
    ) -> User:
        technician = await self._technicians.get(user_id)
        if technician is None:
            raise CatalogValidationError(f"technician {user_id} does not exist")

        changes = payload.model_dump(exclude_unset=True)

        shift_id = changes.get("shift_id")
        if shift_id is not None and await self._shifts.get(shift_id) is None:
            raise CatalogValidationError(f"shift {shift_id} does not exist")

        if "specialty_ids" in changes and changes["specialty_ids"] is not None:
            wanted = list(dict.fromkeys(changes["specialty_ids"]))
            found = await self._specialties.get_many(wanted)
            missing = set(wanted) - {s.id for s in found}
            if missing:
                raise CatalogValidationError(
                    "unknown specialties: " + ", ".join(sorted(str(m) for m in missing))
                )
            technician.specialties = found

        for field in ("support_level", "shift_id", "max_load"):
            if field in changes:
                setattr(technician, field, changes[field])

        return await self._technicians.save(technician)
