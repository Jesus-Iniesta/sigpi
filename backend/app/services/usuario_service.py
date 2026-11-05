"""Use cases for provisioning and maintaining user accounts (HU-10.1)."""

import uuid
from typing import Any

from app.core.exceptions import BusinessRuleError
from app.core.permissions import RoleName
from app.core.security import hash_password, is_institutional_email
from app.domain.auditoria import AuditContext, campos_modificados, snapshot
from app.domain.directory import DirectoryClient
from app.models.identity import User
from app.repositories.usuario_repository import UsuarioRepository
from app.services.auditoria_service import AuditoriaService

ENTIDAD_USUARIO = "user"
# Campos del usuario que se guardan en la bitácora; `password_hash` nunca se incluye.
CAMPOS_AUDITADOS_USUARIO: tuple[str, ...] = (
    "id",
    "institutional_id",
    "full_name",
    "email",
    "user_type",
    "unit_id",
    "max_load",
    "is_active",
)


def _snapshot_usuario(user: User) -> dict[str, Any]:
    datos = snapshot(user, CAMPOS_AUDITADOS_USUARIO)
    datos["roles"] = sorted(ur.role.name for ur in user.roles if ur.role is not None)
    return datos


class UnknownDirectoryAccountError(LookupError):
    """Raised when the institutional directory has no record of the account (RN-02)."""


class DuplicateUserError(ValueError):
    """Raised when the account is already registered in SIGPI."""


class NonInstitutionalEmailError(BusinessRuleError):
    """El directorio devolvió un correo que no es institucional (HU-10.1)."""

    code = "non_institutional_email"
    default_message = "El correo debe ser institucional (@uaemex.mx o @alumno.uaemex.mx)."


class RoleNotConfiguredError(LookupError):
    """Raised when the requested role has not been seeded into the database."""


class UsuarioService:
    def __init__(
        self,
        repository: UsuarioRepository,
        directory: DirectoryClient,
        auditoria: AuditoriaService,
    ) -> None:
        self.repository = repository
        self.directory = directory
        self.auditoria = auditoria

    async def create_user(
        self,
        *,
        institutional_id: str,
        password: str,
        role: RoleName,
        unit_id: uuid.UUID | None = None,
        max_load: int | None = None,
        contexto: AuditContext | None = None,
    ) -> User:
        existing = await self.repository.get_by_institutional_id(institutional_id)
        if existing is not None:
            raise DuplicateUserError(f"La cuenta {institutional_id} ya está registrada en SIGPI.")

        profile = await self.directory.fetch_profile(institutional_id)
        if profile is None:
            raise UnknownDirectoryAccountError(
                f"El directorio institucional no reconoce la cuenta {institutional_id}."
            )
        if not is_institutional_email(profile.email):
            raise NonInstitutionalEmailError(
                f"El correo {profile.email} de la cuenta {institutional_id} no es institucional "
                "(@uaemex.mx o @alumno.uaemex.mx)."
            )

        role_row = await self.repository.get_role_by_name(role)
        if role_row is None:
            raise RoleNotConfiguredError(f"El rol {role.value} no está configurado.")

        user = User(
            institutional_id=profile.institutional_id,
            full_name=profile.full_name,
            email=profile.email,
            password_hash=hash_password(password),
            user_type=profile.user_type,
            unit_id=unit_id,
            max_load=max_load,
            is_active=True,
        )
        created = await self.repository.add(user)
        await self.repository.assign_role(created.id, role_row.id)
        loaded = await self.repository.get_by_id(created.id)
        assert loaded is not None
        await self.auditoria.registrar(
            contexto,
            action="usuario.creado",
            entity_type=ENTIDAD_USUARIO,
            entity_id=loaded.id,
            new_values=_snapshot_usuario(loaded),
        )
        await self.repository.commit()
        return loaded

    async def deactivate_user(
        self, user_id: uuid.UUID, contexto: AuditContext | None = None
    ) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise LookupError(f"No existe un usuario con id {user_id}.")
        antes = _snapshot_usuario(user)
        deactivated = await self.repository.deactivate(user)
        old_values, new_values = campos_modificados(antes, _snapshot_usuario(deactivated))
        await self.auditoria.registrar(
            contexto,
            action="usuario.desactivado",
            entity_type=ENTIDAD_USUARIO,
            entity_id=deactivated.id,
            old_values=old_values,
            new_values=new_values,
        )
        await self.repository.commit()
        return deactivated

    async def list_active_users(self) -> list[User]:
        return await self.repository.list_active()

    async def update_user(
        self,
        user_id: uuid.UUID,
        updates: dict[str, Any],
        contexto: AuditContext | None = None,
    ) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise LookupError(f"No existe un usuario con id {user_id}.")
        antes = _snapshot_usuario(user)

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
        old_values, new_values = campos_modificados(antes, _snapshot_usuario(refreshed))
        await self.auditoria.registrar(
            contexto,
            action="usuario.modificado",
            entity_type=ENTIDAD_USUARIO,
            entity_id=refreshed.id,
            old_values=old_values,
            new_values=new_values,
        )
        await self.repository.commit()
        return refreshed
