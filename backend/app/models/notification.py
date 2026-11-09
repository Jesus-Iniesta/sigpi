import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import NotificationImportance, NotificationStatus

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.request import Request


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_code: Mapped[str] = mapped_column(String(80), unique=True)
    subject_template: Mapped[str] = mapped_column(String(240))
    body_template: Mapped[str] = mapped_column(Text)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_recipient_read", "recipient_id", "read_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("notification_templates.id"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("service_requests.id"))
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(30))
    subject: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[NotificationStatus] = mapped_column(
        String(20), default=NotificationStatus.PENDING
    )
    importance: Mapped[NotificationImportance] = mapped_column(
        String(10), default=NotificationImportance.NORMAL, server_default="normal"
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    template: Mapped["NotificationTemplate | None"] = relationship()
    request: Mapped["Request | None"] = relationship()
    recipient: Mapped["User"] = relationship()
