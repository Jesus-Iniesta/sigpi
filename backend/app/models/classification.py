import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ClassificationSource

if TYPE_CHECKING:
    from app.models.catalog import Categoria
    from app.models.identity import User
    from app.models.request import Request


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(60), unique=True)
    artifact_uri: Mapped[str | None] = mapped_column(String(300))
    accuracy: Mapped[float | None] = mapped_column(Numeric(5, 4))
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(default=False)


class ClassificationResult(Base):
    __tablename__ = "classification_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_requests.id"), index=True)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_versions.id"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    source: Mapped[ClassificationSource] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Numeric(5, 4))
    urgency: Mapped[int] = mapped_column()
    impact: Mapped[int] = mapped_column()
    justification: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    request: Mapped["Request"] = relationship()
    model_version: Mapped["ModelVersion | None"] = relationship()
    category: Mapped["Categoria | None"] = relationship()


class ClassificationCorrection(Base):
    __tablename__ = "classification_corrections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classification_results.id"))
    corrected_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    corrected_category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    corrected_urgency: Mapped[int | None] = mapped_column()
    corrected_impact: Mapped[int | None] = mapped_column()
    justification: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    result: Mapped[ClassificationResult] = relationship()
    corrected_by: Mapped["User"] = relationship()
    corrected_category: Mapped["Categoria | None"] = relationship()
