"""Application service for recording changes in the audit trail."""

import uuid
from datetime import datetime
from typing import Any

from app.domain.auditoria import AuditContext, a_json
from app.models.auditoria import Auditoria
from app.repositories.auditoria_repository import AuditoriaRepository


class AuditoriaService:
    """Records immutable before/after snapshots for a business change.

    El registro se agrega a la transacción del cambio de negocio; quien orquesta
    el caso de uso hace el `commit` de ambos.
    """

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
            old_values=a_json(old_values) if old_values is not None else None,
            new_values=a_json(new_values) if new_values is not None else None,
            ip_address=ip_address,
        )
        if created_at is not None:
            entry.created_at = created_at
        return await self._repository.add(entry)

    async def registrar(
        self,
        contexto: AuditContext | None,
        *,
        action: str,
        entity_type: str,
        entity_id: str | uuid.UUID,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
    ) -> Auditoria:
        """Registra un cambio con el autor y la IP del contexto de la petición."""
        contexto = contexto or AuditContext()
        return await self.registrar_cambio(
            actor_id=contexto.actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=old_values,
            new_values=new_values,
            ip_address=contexto.ip_address,
        )

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

    async def consultar(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[Auditoria]:
        """Consulta de solo lectura de la bitácora, en orden cronológico."""
        return await self._repository.list_entries(entity_type=entity_type, entity_id=entity_id)
