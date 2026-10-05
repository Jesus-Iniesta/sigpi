"""Immutable audit trail persistence model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.identity import User


class Auditoria(Base):
    """Append-only record of a relevant operation in the platform.

    The append-only guarantee is enforced by the database migration through
    a trigger; this model intentionally exposes no update or delete workflow.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(80))
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    actor: Mapped["User | None"] = relationship()


# Backwards-compatible English name used by existing imports.
AuditLog = Auditoria
