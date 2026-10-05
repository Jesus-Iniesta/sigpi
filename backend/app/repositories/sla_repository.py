import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Categoria
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion


class SlaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_agreements(self) -> list[ServiceLevelAgreement]:
        result = await self._session.scalars(
            select(ServiceLevelAgreement).order_by(ServiceLevelAgreement.name)
        )
        return list(result)

    async def get_agreement(self, agreement_id: uuid.UUID) -> ServiceLevelAgreement | None:
        return await self._session.get(ServiceLevelAgreement, agreement_id)

    async def category_exists(self, category_id: uuid.UUID) -> bool:
        category = await self._session.get(Categoria, category_id)
        return category is not None

    async def find_active_for_category(
        self, category_id: uuid.UUID
    ) -> ServiceLevelAgreement | None:
        result = await self._session.scalars(
            select(ServiceLevelAgreement).where(
                ServiceLevelAgreement.category_id == category_id,
                ServiceLevelAgreement.is_active.is_(True),
            )
        )
        return result.first()

    async def find_default(self) -> ServiceLevelAgreement | None:
        result = await self._session.scalars(
            select(ServiceLevelAgreement).where(
                ServiceLevelAgreement.is_default.is_(True),
                ServiceLevelAgreement.is_active.is_(True),
            )
        )
        return result.first()

    async def add_agreement(self, agreement: ServiceLevelAgreement) -> ServiceLevelAgreement:
        self._session.add(agreement)
        await self._session.commit()
        await self._session.refresh(agreement)
        return agreement

    async def latest_version_number(self, agreement_id: uuid.UUID) -> int:
        result = await self._session.scalar(
            select(func.max(ServiceLevelVersion.version)).where(
                ServiceLevelVersion.agreement_id == agreement_id
            )
        )
        return result or 0

    async def open_version(
        self, agreement_id: uuid.UUID, priority: str
    ) -> ServiceLevelVersion | None:
        """Versión vigente sin fecha de término para la prioridad indicada."""
        result = await self._session.scalars(
            select(ServiceLevelVersion)
            .where(
                ServiceLevelVersion.agreement_id == agreement_id,
                ServiceLevelVersion.priority == priority,
                ServiceLevelVersion.valid_to.is_(None),
            )
            .order_by(ServiceLevelVersion.version.desc())
        )
        return result.first()

    async def list_versions(
        self, agreement_id: uuid.UUID, *, priority: str | None = None
    ) -> list[ServiceLevelVersion]:
        query = (
            select(ServiceLevelVersion)
            .where(ServiceLevelVersion.agreement_id == agreement_id)
            .order_by(ServiceLevelVersion.version.desc(), ServiceLevelVersion.priority)
        )
        if priority is not None:
            query = query.where(ServiceLevelVersion.priority == priority)
        return list(await self._session.scalars(query))

    async def find_effective(
        self, agreement_id: uuid.UUID, priority: str, at: datetime
    ) -> ServiceLevelVersion | None:
        result = await self._session.scalars(
            select(ServiceLevelVersion)
            .where(
                ServiceLevelVersion.agreement_id == agreement_id,
                ServiceLevelVersion.priority == priority,
                ServiceLevelVersion.valid_from <= at,
                (ServiceLevelVersion.valid_to.is_(None)) | (ServiceLevelVersion.valid_to > at),
            )
            .order_by(ServiceLevelVersion.valid_from.desc())
        )
        return result.first()

    async def save_versions(self, versions: list[ServiceLevelVersion]) -> list[ServiceLevelVersion]:
        """Guarda las versiones nuevas y los cierres pendientes en una sola transacción."""
        self._session.add_all(versions)
        await self._session.commit()
        for version in versions:
            await self._session.refresh(version)
        return versions
