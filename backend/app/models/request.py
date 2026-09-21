import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    EscalationStatus,
    EscalationType,
    Priority,
    RequestChannel,
    RequestStatus,
)

if TYPE_CHECKING:
    from app.models.catalog import Categoria
    from app.models.identity import User
    from app.models.inventory import Asset
    from app.models.sla import ServiceLevelVersion


class Request(Base):
    __tablename__ = "service_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id"))
    service_level_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_level_versions.id")
    )
    related_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("service_requests.id"))
    folio: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    physical_location: Mapped[str] = mapped_column(String(240))
    channel: Mapped[RequestChannel] = mapped_column(String(20))
    status: Mapped[RequestStatus] = mapped_column(String(30), default=RequestStatus.REGISTERED)
    priority: Mapped[Priority | None] = mapped_column(String(2))
    urgency: Mapped[int | None] = mapped_column(Integer)
    impact: Mapped[int | None] = mapped_column(Integer)
    classification_confidence: Mapped[float | None] = mapped_column()
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    requester: Mapped["User"] = relationship()
    category: Mapped["Categoria | None"] = relationship()
    asset: Mapped["Asset | None"] = relationship()
    service_level_version: Mapped["ServiceLevelVersion | None"] = relationship()
    related_request: Mapped["Request | None"] = relationship(remote_side=[id])
    logs: Mapped[list["RequestLog"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    assignments: Mapped[list["RequestAssignment"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    escalations: Mapped[list["RequestEscalation"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_requests.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    previous_status: Mapped[RequestStatus | None] = mapped_column(String(30))
    new_status: Mapped[RequestStatus | None] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    request: Mapped[Request] = relationship(back_populates="logs")
    author: Mapped["User"] = relationship()


class RequestAssignment(Base):
    __tablename__ = "request_assignments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_requests.id"), index=True)
    technician_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    score: Mapped[float | None] = mapped_column()
    score_breakdown: Mapped[str | None] = mapped_column(Text)
    is_automatic: Mapped[bool] = mapped_column(Boolean, default=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    request: Mapped[Request] = relationship(back_populates="assignments")
    technician: Mapped["User"] = relationship()


class RequestEscalation(Base):
    __tablename__ = "request_escalations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_requests.id"), index=True)
    requested_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    escalation_type: Mapped[EscalationType] = mapped_column(String(20))
    status: Mapped[EscalationStatus] = mapped_column(String(20), default=EscalationStatus.REQUESTED)
    evidence: Mapped[str] = mapped_column(Text)
    justification: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    request: Mapped[Request] = relationship(back_populates="escalations")
    requested_by: Mapped["User"] = relationship(foreign_keys=[requested_by_id])
    approved_by: Mapped["User | None"] = relationship(foreign_keys=[approved_by_id])
