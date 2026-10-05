import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import SupportLevel

MINUTES_PER_DAY = 24 * 60


class ServiceAreaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)


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
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    area_id: uuid.UUID
    name: str
    description: str | None
    is_active: bool


class SpecialtyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)


class SpecialtyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    is_active: bool


class ShiftCreate(BaseModel):
    """Shift expressed in minutes from midnight (e.g. 07:00 = 420)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    start_minute: int = Field(ge=0, lt=MINUTES_PER_DAY)
    end_minute: int = Field(gt=0, le=MINUTES_PER_DAY)

    @model_validator(mode="after")
    def _end_after_start(self) -> "ShiftCreate":
        if self.end_minute <= self.start_minute:
            raise ValueError("end_minute must be greater than start_minute")
        return self


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
    max_load: int | None = Field(default=None, ge=1, le=50)
    specialty_ids: list[uuid.UUID] | None = None


class TechnicianRead(BaseModel):
    id: uuid.UUID
    full_name: str
    support_level: SupportLevel | None
    shift_id: uuid.UUID | None
    max_load: int | None
    is_active: bool
    specialty_ids: list[uuid.UUID]
