"""HTTP endpoints de autenticación (S3-03, HU-01.1)."""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.models.identity import User
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.identity import UserRead
from app.services.auth_service import (
    AuthService,
    InactiveAccountError,
    InvalidCredentialsError,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(AuthRepository(session))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, service: AuthService = Depends(get_auth_service)):
    try:
        token, user = await service.login(payload.email, payload.password)
    except InvalidCredentialsError as exc:
        # `detail` sigue siendo texto, como en el resto de la API, para que el cliente
        # del frontend lo muestre igual; los campos extra activan la recuperación (AC3).
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "detail": str(exc),
                "failed_attempts": exc.failed_attempts,
                "offer_password_recovery": exc.offer_password_recovery,
            },
        )
    except InactiveAccountError as exc:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})
    return TokenResponse(access_token=token, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
async def read_current_user(user: User = Depends(get_current_user)) -> User:
    return user
