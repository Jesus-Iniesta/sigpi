import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import Priority, RequestChannel, RequestStatus, WaitReason


class RequestCreate(BaseModel):
    """Fields accepted when a requester submits a new service request."""

    model_config = ConfigDict(extra="forbid")

    requester_id: uuid.UUID | None = None
    requester_institutional_id: str | None = Field(default=None, min_length=1, max_length=80)
    category_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    related_request_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=1)
    physical_location: str = Field(min_length=1, max_length=240)
    channel: RequestChannel = RequestChannel.PORTAL
    urgency: int | None = Field(default=None, ge=1, le=3)
    impact: int | None = Field(default=None, ge=1, le=3)

    @field_validator("requester_institutional_id")
    @classmethod
    def _strip_institutional_id(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @model_validator(mode="after")
    def _exactly_one_requester_reference(self) -> "RequestCreate":
        if (self.requester_id is None) == (self.requester_institutional_id is None):
            raise ValueError(
                "indica requester_id o requester_institutional_id, pero no ambos ni ninguno"
            )
        return self


class RequestAssistedCreate(RequestCreate):
    """Fields accepted when a technician registers a request on behalf of a requester (HU-01.3).

    Same data as `RequestCreate`, but the origin channel is mandatory and can only be
    `phone` or `in_person`: the portal channel is reserved for requesters themselves.
    """

    channel: Literal[RequestChannel.PHONE, RequestChannel.IN_PERSON]


class RequestUpdate(BaseModel):
    """Mutable request fields; workflow state changes use dedicated services."""

    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    related_request_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, min_length=1)
    physical_location: str | None = Field(default=None, min_length=1, max_length=240)
    urgency: int | None = Field(default=None, ge=1, le=3)
    impact: int | None = Field(default=None, ge=1, le=3)


class RequestRead(BaseModel):
    """Public representation of a service request returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requester_id: uuid.UUID | None
    requester_institutional_id: str | None
    category_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    service_level_version_id: uuid.UUID | None
    related_request_id: uuid.UUID | None
    folio: str
    title: str
    description: str
    physical_location: str
    channel: RequestChannel
    status: RequestStatus
    priority: Priority | None
    urgency: int | None
    impact: int | None
    classification_confidence: float | None
    first_response_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RequestListItem(BaseModel):
    """Compact representation for list and search responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    folio: str
    title: str
    status: RequestStatus
    priority: Priority | None
    category_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class RequestLogCreate(BaseModel):
    """Fields accepted when appending a new entry to a request's bitácora."""

    model_config = ConfigDict(extra="forbid")

    request_id: uuid.UUID
    author_id: uuid.UUID
    previous_status: RequestStatus | None = None
    new_status: RequestStatus | None = None
    action: str = Field(min_length=1, max_length=120)
    notes: str | None = None


class RequestLogRead(BaseModel):
    """Public representation of a bitácora entry returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: uuid.UUID
    author_id: uuid.UUID
    previous_status: RequestStatus | None
    new_status: RequestStatus | None
    action: str
    notes: str | None
    created_at: datetime


class RequestWaitCreate(BaseModel):
    """Datos para pasar una solicitud a «En espera» y suspender el reloj del SLA."""

    model_config = ConfigDict(extra="forbid")

    reason: WaitReason
    detail: str | None = Field(default=None, min_length=1, max_length=500)
