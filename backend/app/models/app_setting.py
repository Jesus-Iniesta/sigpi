"""Ajustes de la aplicación que se cambian en caliente (S5-06, HU-12.1)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSetting(Base):
    """Un ajuste por clave; si no hay fila, se usa el valor de `Settings`."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
