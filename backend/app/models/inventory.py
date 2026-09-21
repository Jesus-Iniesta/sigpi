import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AssetStatus

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.organization import OrganizationalUnit


class PhysicalSpace(Base):
    __tablename__ = "physical_spaces"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizational_units.id"))
    name: Mapped[str] = mapped_column(String(140))
    building: Mapped[str] = mapped_column(String(120))
    space_type: Mapped[str] = mapped_column(String(50))
    class_schedule: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    unit: Mapped["OrganizationalUnit | None"] = relationship()


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("physical_spaces.id"))
    identifier: Mapped[str] = mapped_column(String(80), unique=True)
    asset_type: Mapped[str] = mapped_column(String(80))
    brand: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(120), unique=True)
    institutional_inventory_number: Mapped[str | None] = mapped_column(String(120), unique=True)
    status: Mapped[AssetStatus] = mapped_column(String(35), default=AssetStatus.ACTIVE)
    physical_condition: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    space: Mapped["PhysicalSpace | None"] = relationship()
    custodies: Mapped[list["AssetCustody"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )


class AssetCustody(Base):
    __tablename__ = "asset_custodies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), index=True)
    custodian_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[date] = mapped_column(Date)
    returned_at: Mapped[date | None] = mapped_column(Date)
    acceptance_signature: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    asset: Mapped[Asset] = relationship(back_populates="custodies")
    custodian: Mapped["User"] = relationship()
