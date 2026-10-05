"""Application service for recording changes in the audit trail."""

import uuid
from datetime import datetime
from typing import Any

from app.models.auditoria import Auditoria
from app.repositories.auditoria_repository import AuditoriaRepository


class AuditoriaService:
    """Records immutable before/after snapshots for a business change."""

    def __init__(self, repository: AuditoriaRepository) -> None:
        self._repository = repository

    async def registrar_cambio(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: str | uuid.UUID,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
        ip_address: str | None = None,
        created_at: datetime | None = None,
    ) -> Auditoria:
        entry = Auditoria(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
        )
        if created_at is not None:
            entry.created_at = created_at
        return await self._repository.add(entry)

    async def record_change(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: str | uuid.UUID,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
        ip_address: str | None = None,
        created_at: datetime | None = None,
    ) -> Auditoria:
        """English alias for integrations that use the platform API in English."""
        return await self.registrar_cambio(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            created_at=created_at,
        )

    async def historial_entidad(
        self,
        *,
        entity_type: str,
        entity_id: str | uuid.UUID,
    ) -> list[Auditoria]:
        return await self._repository.list_for_entity(
            entity_type=entity_type,
            entity_id=str(entity_id),
        )
