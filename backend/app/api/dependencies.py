"""Dependencias de FastAPI para identificar al usuario, exigir permisos (S3-03) y armar
el contexto de auditoría de cada petición (S2-08)."""

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission, has_permission
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_session
from app.domain.auditoria import AuditContext
from app.models.identity import User
from app.repositories.auth_repository import AuthRepository

__all__ = ["AuditContext", "get_audit_context", "get_current_user", "require_permission"]

bearer_scheme = HTTPBearer(auto_error=False)

# Longitud de la columna `audit_logs.ip_address` (cabe una IPv6 completa).
_IP_MAX_LENGTH = 45

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Debes iniciar sesión para continuar.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    access_token_cookie: str | None = Cookie(default=None, alias="access_token"),
    session: AsyncSession = Depends(get_session),
) -> User:
    token = credentials.credentials if credentials else access_token_cookie
    if token is None:
        raise _UNAUTHENTICATED
    try:
        payload = decode_access_token(token)
    except InvalidTokenError as exc:
        raise _UNAUTHENTICATED from exc
    user = await AuthRepository(session).get_by_id(payload.user_id)
    if user is None or not user.is_active:
        raise _UNAUTHENTICATED
    return user


def require_permission(permission: Permission):
    """Dependencia que deja pasar solo a usuarios con algún rol que otorgue el permiso."""

    async def checker(user: User = Depends(get_current_user)) -> User:
        role_names = [ur.role.name for ur in user.roles if ur.role is not None]
        if not any(has_permission(role, permission) for role in role_names):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para realizar esta acción.",
            )
        return user

    return checker


def client_ip(request: Request) -> str | None:
    """IP de origen: el primer salto de `X-Forwarded-For` o, si no viene, la del socket."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:_IP_MAX_LENGTH]
    if request.client is None:
        return None
    return request.client.host[:_IP_MAX_LENGTH]


async def get_audit_context(
    request: Request, user: User = Depends(get_current_user)
) -> AuditContext:
    """Autor (usuario en sesión) e IP que se registran en la bitácora de auditoría."""
    return AuditContext(actor_id=user.id, ip_address=client_ip(request))
