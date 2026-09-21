import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import MaintenanceStatus, MaintenanceType

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.inventory import Asset, PhysicalSpace


class MaintenanceOrder(Base):
    __tablename__ = "maintenance_orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("physical_spaces.id"))
    responsible_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    order_number: Mapped[str] = mapped_column(String(50), unique=True)
    maintenance_type: Mapped[MaintenanceType] = mapped_column(String(20))
    scheduled_date: Mapped[date] = mapped_column(Date)
    status: Mapped[MaintenanceStatus] = mapped_column(String(20), default=MaintenanceStatus.PLANNED)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    space: Mapped["PhysicalSpace"] = relationship()
    responsible: Mapped["User"] = relationship()
    acts: Mapped[list["MaintenanceAct"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class MaintenanceAct(Base):
    __tablename__ = "maintenance_acts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("maintenance_orders.id"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"))
    technician_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    findings: Mapped[str | None] = mapped_column(Text)
    parts_used: Mapped[str | None] = mapped_column(Text)
    execution_signature: Mapped[str | None] = mapped_column(Text)
    conformity_signature: Mapped[str | None] = mapped_column(Text)
    next_maintenance_date: Mapped[date | None] = mapped_column(Date)

    order: Mapped[MaintenanceOrder] = relationship(back_populates="acts")
    asset: Mapped["Asset"] = relationship()
    technician: Mapped["User"] = relationship()
