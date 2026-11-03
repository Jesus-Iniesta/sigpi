import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.core.exceptions import BusinessRuleError
from app.domain.catalog_options import (
    CATEGORY_OPTIONS,
    MAX_LOAD_MAX,
    MAX_LOAD_MIN,
    SERVICE_AREA_OPTIONS,
    SHIFT_OPTIONS,
    CatalogOptionError,
    ensure_option,
    validate_description,
)
from app.models.enums import SupportLevel


class CatalogOptionNotAllowedError(BusinessRuleError):
    """El nombre enviado no pertenece a las opciones predefinidas del catálogo (COR-04)."""

    code = "catalog_option_not_allowed"
    default_message = "El valor no pertenece a las opciones permitidas del catálogo."


def _strip_text(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _strip_description(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None
    return value


def _allowed(label: str, value: str, allowed: tuple[str, ...]) -> str:
    # Se lanza un error de negocio (no ValueError) para que la respuesta lleve
    # el código estable `catalog_option_not_allowed` y no `validation_error`.
    try:
        return ensure_option(label, value, allowed)
    except CatalogOptionError as exc:
        raise CatalogOptionNotAllowedError(str(exc)) from exc


OptionName = Annotated[str, BeforeValidator(_strip_text), Field(min_length=1, max_length=120)]

Description = Annotated[
    str | None,
    BeforeValidator(_strip_description),
    AfterValidator(lambda value: None if value is None else validate_description(value)),
]


class ServiceAreaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_id: uuid.UUID
    name: OptionName
    description: Description = None

    @field_validator("name")
    @classmethod
    def _name_in_options(cls, value: str) -> str:
        return _allowed("el área de servicio", value, SERVICE_AREA_OPTIONS)


class OrganizationalUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    unit_type: str
    code: str | None


class ServiceAreaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    unit_id: uuid.UUID
    name: str
    description: str | None
    is_active: bool


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_id: uuid.UUID
    name: OptionName
    description: Description = None

    @field_validator("name")
    @classmethod
    def _name_in_options(cls, value: str) -> str:
        return _allowed("la categoría", value, CATEGORY_OPTIONS)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    area_id: uuid.UUID
    name: str
    description: str | None
    is_active: bool


class SpecialtyCreate(BaseModel):
    """El nombre se valida contra la categoría en `CatalogService` (necesita consultarla)."""

    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID
    name: OptionName


class SpecialtyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    is_active: bool


class ShiftCreate(BaseModel):
    """Solo se envía el nombre; el servidor fija el horario del turno predefinido."""

    model_config = ConfigDict(extra="forbid")

    name: OptionName

    @field_validator("name")
    @classmethod
    def _name_in_options(cls, value: str) -> str:
        return _allowed("el turno", value, tuple(option.name for option in SHIFT_OPTIONS))


class ShiftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    start_minute: int
    end_minute: int
    is_active: bool


class TechnicianProfileUpdate(BaseModel):
    """Mutable technician attributes used by the assignment engine (RN-08)."""

    model_config = ConfigDict(extra="forbid")

    support_level: SupportLevel | None = None
    shift_id: uuid.UUID | None = None
    max_load: int | None = Field(default=None, ge=MAX_LOAD_MIN, le=MAX_LOAD_MAX)
    specialty_ids: list[uuid.UUID] | None = None


class TechnicianRead(BaseModel):
    id: uuid.UUID
    full_name: str
    support_level: SupportLevel | None
    shift_id: uuid.UUID | None
    max_load: int | None
    is_active: bool
    specialty_ids: list[uuid.UUID]


class ShiftOptionRead(BaseModel):
    name: str
    start_minute: int
    end_minute: int


class SpecialtyOptionsRead(BaseModel):
    category: str
    names: list[str]


class MaxLoadRange(BaseModel):
    min: int
    max: int


class CatalogOptionsRead(BaseModel):
    """Listas cerradas del catálogo para que el frontend no las duplique."""

    service_areas: list[str]
    categories: list[str]
    specialties: list[SpecialtyOptionsRead]
    shifts: list[ShiftOptionRead]
    max_load: MaxLoadRange
