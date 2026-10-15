"""Dependencias de FastAPI para identificar al usuario y exigir permisos (S3-03)."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission, has_permission
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_session
from app.models.identity import User
from app.repositories.auth_repository import AuthRepository

bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Debes iniciar sesión para continuar.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise _UNAUTHENTICATED
    try:
        payload = decode_access_token(credentials.credentials)
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
