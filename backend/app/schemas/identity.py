"""Pydantic contracts for user accounts and role assignments."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.permissions import RoleName
from app.models.enums import SupportLevel, UserType


class UserCreate(BaseModel):
    """Fields accepted when provisioning a new account from the directory."""

    model_config = ConfigDict(extra="forbid")

    institutional_id: str = Field(min_length=1, max_length=80)
    role: RoleName
    unit_id: uuid.UUID | None = None
    max_load: int | None = Field(default=None, ge=0)


class UserRead(BaseModel):
    """Public representation of a user account, with roles flattened to their names."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    institutional_id: str
    full_name: str
    email: str
    user_type: UserType
    support_level: SupportLevel | None
    is_active: bool
    max_load: int | None
    roles: list[str]
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _flatten_roles(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        role_names = [ur.role.name for ur in getattr(data, "roles", []) if ur.role is not None]
        return {
            "id": data.id,
            "institutional_id": data.institutional_id,
            "full_name": data.full_name,
            "email": data.email,
            "user_type": data.user_type,
            "support_level": data.support_level,
            "is_active": data.is_active,
            "max_load": data.max_load,
            "roles": role_names,
            "created_at": data.created_at,
            "updated_at": data.updated_at,
        }