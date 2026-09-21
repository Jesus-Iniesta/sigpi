import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Priority, RequestChannel, RequestStatus


class RequestCreate(BaseModel):
    """Fields accepted when a requester submits a new service request."""

    model_config = ConfigDict(extra="forbid")

    requester_id: uuid.UUID
    category_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    related_request_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=1)
    physical_location: str = Field(min_length=1, max_length=240)
    channel: RequestChannel = RequestChannel.PORTAL
    urgency: int | None = Field(default=None, ge=1, le=3)
    impact: int | None = Field(default=None, ge=1, le=3)


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
    requester_id: uuid.UUID
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
