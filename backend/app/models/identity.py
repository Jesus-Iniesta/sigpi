import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SupportLevel, UserType

if TYPE_CHECKING:
    from app.models.catalog import Especialidad, Turno
    from app.models.organization import OrganizationalUnit


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizational_units.id"))
    institutional_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(180))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    user_type: Mapped[UserType] = mapped_column(String(30), default=UserType.ADMINISTRATIVE)
    support_level: Mapped[SupportLevel | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_load: Mapped[int | None] = mapped_column()
    shift_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shifts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    unit: Mapped["OrganizationalUnit | None"] = relationship()
    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    shift: Mapped["Turno | None"] = relationship()
    specialties: Mapped[list["Especialidad"]] = relationship(secondary="user_specialties")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str | None] = mapped_column(String(240))

    users: Mapped[list["UserRole"]] = relationship(back_populates="role")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(back_populates="users")


class UserSpecialty(Base):
    """Especialidades que un técnico está habilitado para atender.

    Alimenta al motor de asignación inteligente para determinar los
    técnicos elegibles según la categoría de la incidencia (RN-08).
    """

    __tablename__ = "user_specialties"
    __table_args__ = (UniqueConstraint("user_id", "specialty_id", name="uq_user_specialty"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    specialty_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("specialties.id"), primary_key=True)
