"""Use cases for provisioning and maintaining user accounts (HU-10.1)."""

import uuid
from typing import Any

from app.core.permissions import RoleName
from app.domain.directory import DirectoryClient
from app.models.identity import User
from app.repositories.usuario_repository import UsuarioRepository


class UnknownDirectoryAccountError(LookupError):
    """Raised when the institutional directory has no record of the account (RN-02)."""


class DuplicateUserError(ValueError):
    """Raised when the account is already registered in SIGPI."""


class RoleNotConfiguredError(LookupError):
    """Raised when the requested role has not been seeded into the database."""


class UsuarioService:
    def __init__(self, repository: UsuarioRepository, directory: DirectoryClient) -> None:
        self.repository = repository
        self.directory = directory

    async def create_user(
        self,
        *,
        institutional_id: str,
        role: RoleName,
        unit_id: uuid.UUID | None = None,
        max_load: int | None = None,
    ) -> User:
        existing = await self.repository.get_by_institutional_id(institutional_id)
        if existing is not None:
            raise DuplicateUserError(f"La cuenta {institutional_id} ya está registrada en SIGPI.")

        profile = await self.directory.fetch_profile(institutional_id)
        if profile is None:
            raise UnknownDirectoryAccountError(
                f"El directorio institucional no reconoce la cuenta {institutional_id}."
            )

        role_row = await self.repository.get_role_by_name(role)
        if role_row is None:
            raise RoleNotConfiguredError(f"El rol {role.value} no está configurado.")

        user = User(
            institutional_id=profile.institutional_id,
            full_name=profile.full_name,
            email=profile.email,
            user_type=profile.user_type,
            unit_id=unit_id,
            max_load=max_load,
            is_active=True,
        )
        created = await self.repository.add(user)
        await self.repository.assign_role(created.id, role_row.id)
        loaded = await self.repository.get_by_id(created.id)
        assert loaded is not None
        return loaded

    async def deactivate_user(self, user_id: uuid.UUID) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise LookupError(f"No existe un usuario con id {user_id}.")
        return await self.repository.deactivate(user)

    async def list_active_users(self) -> list[User]:
        return await self.repository.list_active()

    async def update_user(self, user_id: uuid.UUID, updates: dict[str, Any]) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise LookupError(f"No existe un usuario con id {user_id}.")

        role = updates.pop("role", None)
        if role is not None:
            role_row = await self.repository.get_role_by_name(role)
            if role_row is None:
                raise RoleNotConfiguredError(f"El rol {role.value} no está configurado.")
            await self.repository.replace_roles(user.id, role_row.id)

        if updates:
            await self.repository.update_fields(user, updates)

        refreshed = await self.repository.get_by_id(user_id)
        assert refreshed is not None
        return refreshed
