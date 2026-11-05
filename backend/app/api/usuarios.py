"""HTTP endpoints for user account management (HU-10.1)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AuditContext, get_audit_context, require_permission
from app.core.permissions import Permission
from app.db.session import get_session
from app.domain.directory import DirectoryClient
from app.integrations.directory_client import StubDirectoryClient
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.identity import UserCreate, UserRead, UserUpdate
from app.services.auditoria_service import AuditoriaService
from app.services.usuario_service import (
    DuplicateUserError,
    RoleNotConfiguredError,
    UnknownDirectoryAccountError,
    UsuarioService,
)

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


def get_directory_client() -> DirectoryClient:
    # El directorio solo aporta los datos de la cuenta al darla de alta; el acceso
    # lo valida SIGPI con sus propias credenciales (S3-03).
    return StubDirectoryClient()


def get_usuario_service(
    session: AsyncSession = Depends(get_session),
    directory: DirectoryClient = Depends(get_directory_client),
) -> UsuarioService:
    return UsuarioService(
        UsuarioRepository(session), directory, AuditoriaService(AuditoriaRepository(session))
    )


# Las altas, modificaciones y bajas exigen sesión con permiso de administración de cuentas.
_GESTIONA_CUENTAS = [Depends(require_permission(Permission.IDENTITY_MANAGE))]


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=_GESTIONA_CUENTAS,
)
async def create_user(
    payload: UserCreate,
    service: UsuarioService = Depends(get_usuario_service),
    contexto: AuditContext = Depends(get_audit_context),
) -> UserRead:
    try:
        return await service.create_user(
            institutional_id=payload.institutional_id,
            password=payload.password,
            role=payload.role,
            unit_id=payload.unit_id,
            max_load=payload.max_load,
            contexto=contexto,
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


@router.delete("/{user_id}", response_model=UserRead, dependencies=_GESTIONA_CUENTAS)
async def deactivate_user(
    user_id: uuid.UUID,
    service: UsuarioService = Depends(get_usuario_service),
    contexto: AuditContext = Depends(get_audit_context),
) -> UserRead:
    try:
        return await service.deactivate_user(user_id, contexto)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{user_id}", response_model=UserRead, dependencies=_GESTIONA_CUENTAS)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    service: UsuarioService = Depends(get_usuario_service),
    contexto: AuditContext = Depends(get_audit_context),
) -> UserRead:
    try:
        return await service.update_user(user_id, payload.model_dump(exclude_unset=True), contexto)
    except RoleNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
