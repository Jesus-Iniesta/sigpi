import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ArticleStatus

if TYPE_CHECKING:
    from app.models.catalog import Categoria
    from app.models.identity import User
    from app.models.request import Request


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(180))
    symptom: Mapped[str] = mapped_column(Text)
    cause: Mapped[str] = mapped_column(Text)
    procedure: Mapped[str] = mapped_column(Text)
    verification: Mapped[str] = mapped_column(Text)
    status: Mapped[ArticleStatus] = mapped_column(String(30), default=ArticleStatus.DRAFT)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    category: Mapped["Categoria"] = relationship()
    author: Mapped["User"] = relationship()


class KnowledgeSearch(Base):
    __tablename__ = "knowledge_searches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    article_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("knowledge_articles.id"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("service_requests.id"))
    searched_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    query: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    article: Mapped["KnowledgeArticle | None"] = relationship()
    request: Mapped["Request | None"] = relationship()
    searched_by: Mapped["User"] = relationship()
