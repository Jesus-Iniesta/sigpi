"""Contratos de lectura de la bitácora de auditoría (S2-08, HU-10.3)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditoriaRead(BaseModel):
    """Registro de auditoría tal como se guardó; la bitácora es de solo lectura."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str
    old_values: dict[str, Any] | None
    new_values: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime
