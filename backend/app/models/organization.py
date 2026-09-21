import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OrganizationalUnit(Base):
    __tablename__ = "organizational_units"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizational_units.id"))
    name: Mapped[str] = mapped_column(String(160), unique=True)
    unit_type: Mapped[str] = mapped_column(String(60))
    code: Mapped[str | None] = mapped_column(String(40), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    parent: Mapped["OrganizationalUnit | None"] = relationship(
        remote_side=[id], back_populates="children"
    )
    children: Mapped[list["OrganizationalUnit"]] = relationship(back_populates="parent")
