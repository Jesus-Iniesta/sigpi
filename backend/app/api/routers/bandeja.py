"""Bandeja de solicitudes asignadas al técnico en sesión (S5-04, HU-04.6)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.core.exceptions import PermissionDeniedError
from app.core.permissions import Permission, has_permission
from app.db.session import get_session
from app.models.enums import Priority, RequestStatus
from app.models.identity import User
from app.repositories.solicitud_repository import SolicitudRepository
from app.schemas.bandeja import BandejaElemento
from app.services.bandeja_service import BandejaService

router = APIRouter(prefix="/bandeja", tags=["bandeja"])


def get_bandeja_service(session: AsyncSession = Depends(get_session)) -> BandejaService:
    return BandejaService(SolicitudRepository(session))


def _puede_asignar(user: User) -> bool:
    return any(
        ur.role is not None and has_permission(ur.role.name, Permission.REQUESTS_ASSIGN)
        for ur in user.roles
    )


@router.get("", response_model=list[BandejaElemento])
async def list_assigned_requests(
    estatus: RequestStatus | None = Query(default=None),
    prioridad: Priority | None = Query(default=None),
    todas: bool = Query(default=False),
    user: User = Depends(require_permission(Permission.REQUESTS_READ)),
    service: BandejaService = Depends(get_bandeja_service),
) -> list[BandejaElemento]:
    """Solicitudes abiertas con asignación vigente al usuario en sesión.

    Orden: P1 primero y, dentro de la misma prioridad, la fecha compromiso más próxima.
    Con `todas=true`, quien puede asignar (jefe de servicio) ve las de todo el equipo.
    """
    if todas and not _puede_asignar(user):
        raise PermissionDeniedError("Solo quien asigna solicitudes puede ver la bandeja completa.")
    return await service.listar(
        technician_id=None if todas else user.id, status=estatus, priority=prioridad
    )
