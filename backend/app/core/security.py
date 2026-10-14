"""Contraseñas, tokens de acceso y formato del correo institucional (S3-03).

Este módulo es puro: no toca la base de datos ni FastAPI. La dependencia que
identifica al usuario en cada petición vive en `app.api.dependencies`.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import settings

INSTITUTIONAL_EMAIL_DOMAIN = "uaemex.mx"
_INSTITUTIONAL_EMAIL = re.compile(
    rf"^[A-Za-z0-9._%+-]+@{re.escape(INSTITUTIONAL_EMAIL_DOMAIN)}$", re.IGNORECASE
)

_password_hasher = PasswordHash.recommended()


class InvalidTokenError(Exception):
    """El token falta, está mal formado, expiró o fue alterado."""


@dataclass(frozen=True)
class TokenPayload:
    user_id: uuid.UUID
    roles: tuple[str, ...]


def is_institutional_email(email: str) -> bool:
    """True si el correo tiene exactamente el formato `usuario@uaemex.mx`."""
    return _INSTITUTIONAL_EMAIL.fullmatch(email) is not None


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password, password_hash)
    except UnknownHashError:  # hash corrupto o de otro algoritmo: contraseña inválida
        return False


# Hash de relleno: permite gastar el mismo tiempo cuando la cuenta no existe y así
# no revelar por tiempo de respuesta qué correos están registrados.
DUMMY_PASSWORD_HASH = hash_password("sigpi-dummy-password")


def create_access_token(user_id: uuid.UUID, roles: list[str]) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "roles": roles,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    try:
        claims = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return TokenPayload(user_id=uuid.UUID(claims["sub"]), roles=tuple(claims.get("roles", [])))
    except (JWTError, KeyError, ValueError) as exc:
        raise InvalidTokenError("Token inválido o expirado.") from exc
    