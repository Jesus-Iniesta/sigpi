import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import Priority

if TYPE_CHECKING:
    from app.models.catalog import Categoria


class ServiceLevelAgreement(Base):
    __tablename__ = "service_level_agreements"

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
    __table_args__ = (UniqueConstraint("agreement_id", "version", name="uq_sla_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agreement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_level_agreements.id"))
    version: Mapped[int] = mapped_column(Integer)
    priority: Mapped[Priority] = mapped_column(String(2))
    first_response_minutes: Mapped[int] = mapped_column(Integer)
    resolution_minutes: Mapped[int] = mapped_column(Integer)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agreement: Mapped[ServiceLevelAgreement] = relationship(back_populates="versions")
