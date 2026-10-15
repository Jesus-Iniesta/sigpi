"""Caso de uso: iniciar sesión con correo institucional y contraseña (S3-03, HU-01.1)."""

from app.core.config import settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    verify_password,
)
from app.models.identity import User
from app.repositories.auth_repository import AuthRepository


class InvalidCredentialsError(Exception):
    """Correo o contraseña incorrectos.

    `offer_password_recovery` se activa al alcanzar el máximo de intentos fallidos
    seguidos (AC3 de HU-01.1); la interfaz lo usa para mostrar la recuperación.
    """

    def __init__(self, failed_attempts: int, offer_password_recovery: bool) -> None:
        super().__init__("Correo o contraseña incorrectos.")
        self.failed_attempts = failed_attempts
        self.offer_password_recovery = offer_password_recovery


class InactiveAccountError(Exception):
    """La cuenta existe y la contraseña es correcta, pero está desactivada."""


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self.repository = repository

    async def login(self, email: str, password: str) -> tuple[str, User]:
        user = await self.repository.get_by_email(email)

        if user is None or not user.password_hash:
            # Mismo costo de cómputo que una cuenta real; el mensaje no distingue el caso.
            verify_password(password, DUMMY_PASSWORD_HASH)
            raise InvalidCredentialsError(failed_attempts=0, offer_password_recovery=False)

        if not verify_password(password, user.password_hash):
            attempts = user.failed_login_attempts + 1
            await self.repository.set_failed_attempts(user, attempts)
            raise InvalidCredentialsError(
                failed_attempts=attempts,
                offer_password_recovery=attempts >= settings.max_failed_login_attempts,
            )

        if not user.is_active:
            raise InactiveAccountError("La cuenta está desactivada.")

        user_id = user.id
        if user.failed_login_attempts:
            await self.repository.set_failed_attempts(user, 0)

        loaded = await self.repository.get_by_id(user_id)
        assert loaded is not None
        roles = [ur.role.name for ur in loaded.roles if ur.role is not None]
        return create_access_token(user_id, roles), loaded
