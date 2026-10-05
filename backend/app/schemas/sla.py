import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import Priority


class SlaAgreementCreate(BaseModel):
    """Acuerdo de nivel de servicio: de una categoría o el predeterminado."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=140)
    category_id: uuid.UUID | None = None
    is_default: bool = False

    @model_validator(mode="after")
    def _validate_scope(self) -> "SlaAgreementCreate":
        if self.is_default and self.category_id is not None:
            raise ValueError("El acuerdo predeterminado no puede asociarse a una categoría.")
        if not self.is_default and self.category_id is None:
            raise ValueError("Un acuerdo que no es predeterminado requiere una categoría.")
        return self


class SlaAgreementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID | None
    name: str
    is_default: bool
    is_active: bool
    created_at: datetime


class SlaPriorityTimes(BaseModel):
    """Tiempos comprometidos para una prioridad, en minutos."""

    model_config = ConfigDict(extra="forbid")

    priority: Priority
    first_response_minutes: int = Field(gt=0)
    resolution_minutes: int = Field(gt=0)

    @model_validator(mode="after")
    def _resolution_after_first_response(self) -> "SlaPriorityTimes":
        if self.resolution_minutes <= self.first_response_minutes:
            raise ValueError(
                f"Inconsistencia en {self.priority.value}: el tiempo de resolución debe ser "
                "mayor que el de primera respuesta."
            )
        return self


class SlaVersionCreate(BaseModel):
    """Nueva versión del acuerdo, con su fecha de entrada en vigor."""

    model_config = ConfigDict(extra="forbid")

    valid_from: datetime
    times: list[SlaPriorityTimes] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_priorities(self) -> "SlaVersionCreate":
        priorities = [item.priority for item in self.times]
        if len(priorities) != len(set(priorities)):
            raise ValueError("Cada prioridad solo puede aparecer una vez por versión.")
        return self


class SlaVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agreement_id: uuid.UUID
    version: int
    priority: Priority
    first_response_minutes: int
    resolution_minutes: int
    valid_from: datetime
    valid_to: datetime | None


class EffectiveSlaRead(BaseModel):
    """Acuerdo que aplica a una categoría y prioridad en una fecha dada."""

    agreement_id: uuid.UUID
    agreement_name: str
    version: int
    priority: Priority
    first_response_minutes: int
    resolution_minutes: int
    valid_from: datetime
    used_default: bool
    notice: str | None
