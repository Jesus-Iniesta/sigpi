"""HTTP endpoints for user account management (HU-10.1)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.domain.directory import DirectoryClient
from app.integrations.directory_client import StubDirectoryClient
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.identity import UserCreate, UserRead, UserUpdate
from app.services.usuario_service import (
    DuplicateUserError,
    RoleNotConfiguredError,
    UnknownDirectoryAccountError,
    UsuarioService,
)

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


def get_directory_client() -> DirectoryClient:
    # TODO(S3-03): devolver aquí el adaptador real de Microsoft 365.
    return StubDirectoryClient()


def get_usuario_service(
    session: AsyncSession = Depends(get_session),
    directory: DirectoryClient = Depends(get_directory_client),
) -> UsuarioService:
    return UsuarioService(UsuarioRepository(session), directory)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate, service: UsuarioService = Depends(get_usuario_service)
) -> UserRead:
    try:
        return await service.create_user(
            institutional_id=payload.institutional_id,
            role=payload.role,
            unit_id=payload.unit_id,
            max_load=payload.max_load,
        )
    except UnknownDirectoryAccountError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateUserError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RoleNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("", response_model=list[UserRead])
async def list_users(service: UsuarioService = Depends(get_usuario_service)) -> list[UserRead]:
    return await service.list_active_users()


@router.delete("/{user_id}", response_model=UserRead)
async def deactivate_user(
    user_id: uuid.UUID, service: UsuarioService = Depends(get_usuario_service)
) -> UserRead:
    try:
        return await service.deactivate_user(user_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    service: UsuarioService = Depends(get_usuario_service),
) -> UserRead:
    try:
        return await service.update_user(user_id, payload.model_dump(exclude_unset=True))
    except RoleNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
