import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.identity import User


class EducationalProgram(Base):
    __tablename__ = "educational_programs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), unique=True)
    level: Mapped[str] = mapped_column(String(60))
    code: Mapped[str | None] = mapped_column(String(40), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    academic_records: Mapped[list["AcademicRecord"]] = relationship(back_populates="program")


class AcademicRecord(Base):
    __tablename__ = "academic_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("educational_programs.id"))
    enrollment_number: Mapped[str] = mapped_column(String(60), unique=True)
    start_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40))

    student: Mapped["User"] = relationship()
    program: Mapped[EducationalProgram] = relationship(back_populates="academic_records")
