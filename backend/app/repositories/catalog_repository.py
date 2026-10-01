import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import AreaServicio, Categoria, Especialidad, Turno
from app.models.enums import UserType
from app.models.identity import User


class ServiceAreaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[AreaServicio]:
        result = await self._session.scalars(select(AreaServicio).order_by(AreaServicio.name))
        return list(result)

    async def get(self, area_id: uuid.UUID) -> AreaServicio | None:
        return await self._session.get(AreaServicio, area_id)

    async def create(self, area: AreaServicio) -> AreaServicio:
        self._session.add(area)
        await self._session.commit()
        await self._session.refresh(area)
        return area


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, *, area_id: uuid.UUID | None = None) -> list[Categoria]:
        query = select(Categoria).order_by(Categoria.name)
        if area_id is not None:
            query = query.where(Categoria.area_id == area_id)
        return list(await self._session.scalars(query))

    async def get(self, category_id: uuid.UUID) -> Categoria | None:
        return await self._session.get(Categoria, category_id)

    async def create(self, category: Categoria) -> Categoria:
        self._session.add(category)
        await self._session.commit()
        await self._session.refresh(category)
        return category


class SpecialtyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, *, category_id: uuid.UUID | None = None) -> list[Especialidad]:
        query = select(Especialidad).order_by(Especialidad.name)
        if category_id is not None:
            query = query.where(Especialidad.category_id == category_id)
        return list(await self._session.scalars(query))

    async def get_many(self, specialty_ids: list[uuid.UUID]) -> list[Especialidad]:
        if not specialty_ids:
            return []
        result = await self._session.scalars(
            select(Especialidad).where(Especialidad.id.in_(specialty_ids))
        )
        return list(result)

    async def create(self, specialty: Especialidad) -> Especialidad:
        self._session.add(specialty)
        await self._session.commit()
        await self._session.refresh(specialty)
        return specialty


class ShiftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Turno]:
        result = await self._session.scalars(select(Turno).order_by(Turno.start_minute))
        return list(result)

    async def get(self, shift_id: uuid.UUID) -> Turno | None:
        return await self._session.get(Turno, shift_id)

    async def create(self, shift: Turno) -> Turno:
        self._session.add(shift)
        await self._session.commit()
        await self._session.refresh(shift)
        return shift


class TechnicianRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, *, specialty_id: uuid.UUID | None = None) -> list[User]:
        query = (
            select(User)
            .where(User.user_type == UserType.TECHNICAL)
            .options(selectinload(User.specialties))
            .order_by(User.full_name)
        )
        if specialty_id is not None:
            query = query.where(User.specialties.any(Especialidad.id == specialty_id))
        return list(await self._session.scalars(query))

    async def get(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.scalars(
            select(User)
            .where(User.id == user_id, User.user_type == UserType.TECHNICAL)
            .options(selectinload(User.specialties))
        )
        return result.first()

    async def save(self, technician: User) -> User:
        self._session.add(technician)
        await self._session.commit()
        await self._session.refresh(technician, attribute_names=["specialties"])
        return technician
