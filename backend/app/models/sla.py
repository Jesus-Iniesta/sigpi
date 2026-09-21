import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import Priority

if TYPE_CHECKING:
    from app.models.catalog import Categoria


class ServiceLevelAgreement(Base):
    __tablename__ = "service_level_agreements"
    __table_args__ = (Index("ix_sla_category_active", "category_id", "is_active"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String(140))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    category: Mapped["Categoria | None"] = relationship()
    versions: Mapped[list["ServiceLevelVersion"]] = relationship(
        back_populates="agreement", cascade="all, delete-orphan"
    )


class ServiceLevelVersion(Base):
    __tablename__ = "service_level_versions"
    __table_args__ = (
        UniqueConstraint("agreement_id", "version", "priority", name="uq_sla_version_priority"),
        CheckConstraint("version > 0", name="ck_sla_version_positive"),
        CheckConstraint("priority IN ('P1', 'P2', 'P3', 'P4')", name="ck_sla_priority_valid"),
        CheckConstraint("first_response_minutes > 0", name="ck_sla_first_response_positive"),
        CheckConstraint("resolution_minutes > 0", name="ck_sla_resolution_positive"),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_sla_valid_period"),
        Index("ix_sla_version_lookup", "agreement_id", "priority", "valid_from"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agreement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_level_agreements.id"))
    version: Mapped[int] = mapped_column(Integer)
    priority: Mapped[Priority] = mapped_column(String(2))
    first_response_minutes: Mapped[int] = mapped_column(Integer)
    resolution_minutes: Mapped[int] = mapped_column(Integer)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agreement: Mapped[ServiceLevelAgreement] = relationship(back_populates="versions")
