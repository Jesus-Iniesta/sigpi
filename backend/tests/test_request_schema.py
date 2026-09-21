import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.enums import Priority, RequestChannel, RequestStatus
from app.schemas.request import RequestCreate, RequestListItem, RequestRead


def test_request_create_defaults_channel_and_validates_impact_range() -> None:
    request = RequestCreate(
        requester_id=uuid.uuid4(),
        title="No funciona el acceso",
        description="La plataforma rechaza las credenciales.",
        physical_location="Edificio A",
        impact=3,
    )

    assert request.channel is RequestChannel.PORTAL
    assert request.impact == 3

    with pytest.raises(ValidationError):
        RequestCreate(
            requester_id=uuid.uuid4(),
            title="Solicitud",
            description="Descripcion",
            physical_location="Edificio A",
            urgency=4,
        )


def test_request_create_does_not_accept_workflow_fields() -> None:
    with pytest.raises(ValidationError):
        RequestCreate(
            requester_id=uuid.uuid4(),
            title="Solicitud",
            description="Descripcion",
            physical_location="Edificio A",
            status=RequestStatus.CLOSED,
            priority=Priority.P1,
        )


def test_request_read_supports_orm_attributes() -> None:
    now = datetime.now(UTC)
    request = RequestRead(
        id=uuid.uuid4(),
        requester_id=uuid.uuid4(),
        category_id=None,
        asset_id=None,
        service_level_version_id=None,
        related_request_id=None,
        folio="SIG-0001",
        title="Solicitud",
        description="Descripcion",
        physical_location="Edificio A",
        channel=RequestChannel.PORTAL,
        status=RequestStatus.REGISTERED,
        priority=None,
        urgency=None,
        impact=None,
        classification_confidence=None,
        first_response_at=None,
        resolved_at=None,
        closed_at=None,
        created_at=now,
        updated_at=now,
    )
    item = RequestListItem.model_validate(request)

    assert item.folio == "SIG-0001"
    assert item.status is RequestStatus.REGISTERED
