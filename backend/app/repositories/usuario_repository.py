"""Persistence gateway for users and their role assignments."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.permissions import RoleName
from app.models.identity import Role, User, UserRole


class UsuarioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_institutional_id(self, institutional_id: str) -> User | None:
        stmt = (
            select(User)
            .where(User.institutional_id == institutional_id)
            .options(selectinload(User.roles).selectinload(UserRole.role))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.roles).selectinload(UserRole.role))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_role_by_name(self, name: RoleName) -> Role | None:
        stmt = select(Role).where(Role.name == name.value)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def assign_role(self, user_id: uuid.UUID, role_id: uuid.UUID) -> None:
        self.session.add(UserRole(user_id=user_id, role_id=role_id))
        await self.session.commit()

    async def deactivate(self, user: User) -> User:
        user.is_active = False
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def list_active(self) -> list[User]:
        stmt = (
            select(User)
            .where(User.is_active.is_(True))
            .options(selectinload(User.roles).selectinload(UserRole.role))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())