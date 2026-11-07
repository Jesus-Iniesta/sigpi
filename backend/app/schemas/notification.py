"""Contratos de la API de avisos dentro de la aplicación (S4-05)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import NotificationImportance
from app.models.notification import Notification


class NotificationRead(BaseModel):
    """Un aviso tal como lo muestra la campana."""

    id: uuid.UUID
    request_id: uuid.UUID | None
    request_folio: str | None
    subject: str
    body: str
    importance: NotificationImportance
    is_read: bool
    read_at: datetime | None
    created_at: datetime

    @classmethod
    def from_model(cls, aviso: Notification) -> "NotificationRead":
        return cls(
            id=aviso.id,
            request_id=aviso.request_id,
            request_folio=aviso.request.folio if aviso.request is not None else None,
            subject=aviso.subject,
            body=aviso.body,
            importance=NotificationImportance(aviso.importance),
            is_read=aviso.read_at is not None,
            read_at=aviso.read_at,
            created_at=aviso.created_at,
        )


class NotificationUnreadCount(BaseModel):
    unread: int = Field(ge=0)


class NotificationMarkAllResult(BaseModel):
    updated: int = Field(ge=0)
