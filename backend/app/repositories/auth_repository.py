"""Consultas de usuarios que necesita la autenticación (S3-03)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.identity import User, UserRole


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _with_roles(self):
        return select(User).options(selectinload(User.roles).selectinload(UserRole.role))

    async def get_by_email(self, email: str) -> User | None:
        stmt = self._with_roles().where(func.lower(User.email) == email.lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = (
            self._with_roles().where(User.id == user_id).execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def set_failed_attempts(self, user: User, attempts: int) -> None:
        user.failed_login_attempts = attempts
        await self.session.commit()
        