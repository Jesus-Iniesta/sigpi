"""Casos de uso del catálogo de técnicos y áreas de soporte (HU-11.1).

Reglas aplicadas:
- RN-08: un técnico solo puede recibir asignaciones de las especialidades que
  tiene habilitadas; este servicio es la única puerta para declararlas.
- Vigencia inmediata: no hay caché en esta capa; cada consulta llega a la base
  de datos, así que un cambio de turno o de carga máxima aplica en la siguiente
  asignación sin reiniciar el servicio.
"""

import uuid
from typing import Any

from app.domain.auditoria import AuditContext, campos_modificados, snapshot
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
from app.services.auditoria_service import AuditoriaService

CAMPOS_AREA = ("id", "unit_id", "name", "description")
CAMPOS_CATEGORIA = ("id", "area_id", "name", "description")
CAMPOS_ESPECIALIDAD = ("id", "category_id", "name")
CAMPOS_TURNO = ("id", "name", "start_minute", "end_minute")
CAMPOS_TECNICO = ("support_level", "shift_id", "max_load")


def _snapshot_tecnico(technician: User) -> dict[str, Any]:
    datos = snapshot(technician, CAMPOS_TECNICO)
    datos["specialty_ids"] = sorted(str(s.id) for s in technician.specialties)
    return datos


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
        auditoria: AuditoriaService,
    ) -> None:
        self._areas = areas
        self._categories = categories
        self._specialties = specialties
        self._shifts = shifts
        self._technicians = technicians
        self._auditoria = auditoria

    async def _registrar_alta(
        self, contexto: AuditContext | None, tipo: str, entity_type: str, obj: Any, campos
    ) -> None:
        await self._auditoria.registrar(
            contexto,
            action=f"catalogo.{tipo}.creado",
            entity_type=entity_type,
            entity_id=obj.id,
            new_values=snapshot(obj, campos),
        )

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

    async def create_area(
        self, payload: ServiceAreaCreate, contexto: AuditContext | None = None
    ) -> AreaServicio:
        area = AreaServicio(
            unit_id=payload.unit_id, name=payload.name, description=payload.description
        )
        created = await self._areas.create(area)
        await self._registrar_alta(contexto, "area", "service_area", created, CAMPOS_AREA)
        await self._areas.commit()
        return created

    # --- categorías ------------------------------------------------------------
    async def list_categories(self, *, area_id: uuid.UUID | None = None) -> list[Categoria]:
        return await self._categories.list_all(area_id=area_id)

    async def create_category(
        self, payload: CategoryCreate, contexto: AuditContext | None = None
    ) -> Categoria:
        if await self._areas.get(payload.area_id) is None:
            raise CatalogValidationError(f"service area {payload.area_id} does not exist")
        category = Categoria(
            area_id=payload.area_id, name=payload.name, description=payload.description
        )
        created = await self._categories.create(category)
        await self._registrar_alta(contexto, "categoria", "category", created, CAMPOS_CATEGORIA)
        await self._categories.commit()
        return created

    # --- especialidades --------------------------------------------------------
    async def list_specialties(self, *, category_id: uuid.UUID | None = None) -> list[Especialidad]:
        return await self._specialties.list_all(category_id=category_id)

    async def create_specialty(
        self, payload: SpecialtyCreate, contexto: AuditContext | None = None
    ) -> Especialidad:
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
        created = await self._specialties.create(specialty)
        await self._registrar_alta(
            contexto, "especialidad", "specialty", created, CAMPOS_ESPECIALIDAD
        )
        await self._specialties.commit()
        return created

    # --- turnos ----------------------------------------------------------------
    async def list_shifts(self) -> list[Turno]:
        return await self._shifts.list_all()

    async def create_shift(
        self, payload: ShiftCreate, contexto: AuditContext | None = None
    ) -> Turno:
        # El horario no lo envía el cliente: se toma del turno predefinido.
        try:
            option = shift_option(payload.name)
        except CatalogOptionError as exc:
            raise CatalogOptionNotAllowedError(str(exc)) from exc
        shift = Turno(
            name=option.name, start_minute=option.start_minute, end_minute=option.end_minute
        )
        created = await self._shifts.create(shift)
        await self._registrar_alta(contexto, "turno", "shift", created, CAMPOS_TURNO)
        await self._shifts.commit()
        return created

    # --- técnicos --------------------------------------------------------------
    async def list_technicians(self, *, specialty_id: uuid.UUID | None = None) -> list[User]:
        return await self._technicians.list_all(specialty_id=specialty_id)

    async def update_technician_profile(
        self,
        user_id: uuid.UUID,
        payload: TechnicianProfileUpdate,
        contexto: AuditContext | None = None,
    ) -> User:
        technician = await self._technicians.get(user_id)
        if technician is None:
            raise CatalogValidationError(f"technician {user_id} does not exist")
        antes = _snapshot_tecnico(technician)

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

        saved = await self._technicians.save(technician)
        old_values, new_values = campos_modificados(antes, _snapshot_tecnico(saved))
        await self._auditoria.registrar(
            contexto,
            action="catalogo.tecnico.modificado",
            entity_type="technician",
            entity_id=saved.id,
            old_values=old_values,
            new_values=new_values,
        )
        await self._technicians.commit()
        return saved
