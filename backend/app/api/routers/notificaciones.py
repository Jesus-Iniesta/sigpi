import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.models.identity import User
from app.schemas.notification import (
    NotificationMarkAllResult,
    NotificationRead,
    NotificationUnreadCount,
)
from app.services.notificacion_service import NotificacionService

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


def get_notificacion_service(
    session: AsyncSession = Depends(get_session),
) -> NotificacionService:
    return NotificacionService(session)


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    only_unread: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    service: NotificacionService = Depends(get_notificacion_service),
) -> list[NotificationRead]:
    """Avisos de la persona en sesión, del más reciente al más antiguo."""
    avisos = await service.listar(user.id, only_unread=only_unread, limit=limit, offset=offset)
    return [NotificationRead.from_model(aviso) for aviso in avisos]


@router.get("/contador", response_model=NotificationUnreadCount)
async def count_unread_notifications(
    user: User = Depends(get_current_user),
    service: NotificacionService = Depends(get_notificacion_service),
) -> NotificationUnreadCount:
    """Número de avisos sin leer: es el contador de la campana."""
    return NotificationUnreadCount(unread=await service.contar_no_leidos(user.id))


@router.post("/leer-todas", response_model=NotificationMarkAllResult)
async def mark_all_notifications_read(
    user: User = Depends(get_current_user),
    service: NotificacionService = Depends(get_notificacion_service),
) -> NotificationMarkAllResult:
    return NotificationMarkAllResult(updated=await service.marcar_todos_leidos(user.id))


@router.post("/{notification_id}/leer", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: NotificacionService = Depends(get_notificacion_service),
) -> NotificationRead:
    aviso = await service.marcar_leido(user.id, notification_id)
    return NotificationRead.from_model(aviso)
