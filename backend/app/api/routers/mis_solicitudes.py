"""Consulta del solicitante por folio y confirmación de la solución (S4-01, HU-04.3).

El prefijo `/mis-solicitudes` evita chocar con `/solicitudes/{request_id}`, que es la
vista del técnico. Una solicitud de otra persona responde 404, igual que un folio que no
existe, para no revelar que el folio está registrado.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.permissions import Permission
from app.db.session import get_session
from app.models.identity import User
from app.models.request import Request
from app.repositories.solicitud_repository import SolicitudRepository
from app.schemas.mis_solicitudes import MiSolicitudDetalle, MiSolicitudResumen
from app.schemas.request import RequestConfirmCreate
from app.services.seguimiento_service import SeguimientoService
from app.services.sla_clock_service import EstadoInvalidoError

router = APIRouter(prefix="/mis-solicitudes", tags=["mis-solicitudes"])

_NO_ENCONTRADA = "No encontramos una solicitud tuya con ese folio."


def get_solicitud_repository(
    session: AsyncSession = Depends(get_session),
) -> SolicitudRepository:
    return SolicitudRepository(session)


def get_seguimiento_service(
    session: AsyncSession = Depends(get_session),
) -> SeguimientoService:
    return SeguimientoService(session)


async def _propia(repository: SolicitudRepository, folio: str, user: User) -> Request:
    request = await repository.get_by_folio_for_requester(folio, user.id)
    if request is None:
        raise NotFoundError(_NO_ENCONTRADA)
    return request


@router.get("", response_model=list[MiSolicitudResumen])
async def list_my_requests(
    user: User = Depends(require_permission(Permission.REQUESTS_VIEW_OWN)),
    repository: SolicitudRepository = Depends(get_solicitud_repository),
) -> list[MiSolicitudResumen]:
    """Solicitudes del usuario en sesión, de la más reciente a la más antigua."""
    requests = await repository.list_by_requester(user.id)
    return [MiSolicitudResumen.model_validate(r) for r in requests]


@router.get("/{folio}", response_model=MiSolicitudDetalle)
async def get_my_request(
    folio: str,
    user: User = Depends(require_permission(Permission.REQUESTS_VIEW_OWN)),
    repository: SolicitudRepository = Depends(get_solicitud_repository),
) -> MiSolicitudDetalle:
    """Estatus, prioridad, fecha compromiso, técnico y bitácora resumida de un folio propio."""
    return MiSolicitudDetalle.desde_solicitud(await _propia(repository, folio, user))


@router.post("/{folio}/confirmar", response_model=MiSolicitudDetalle)
async def confirm_my_request(
    folio: str,
    payload: RequestConfirmCreate | None = None,
    user: User = Depends(require_permission(Permission.REQUESTS_VIEW_OWN)),
    repository: SolicitudRepository = Depends(get_solicitud_repository),
    service: SeguimientoService = Depends(get_seguimiento_service),
) -> MiSolicitudDetalle:
    """Confirma que la solución funcionó y cierra la solicitud (solo si está «Resuelta»)."""
    request = await _propia(repository, folio, user)
    notes = payload.notes if payload else None
    try:
        await service.confirmar(request.id, user.id, notes)
    except EstadoInvalidoError as exc:
        raise BusinessRuleError(str(exc)) from exc
    return MiSolicitudDetalle.desde_solicitud(await _propia(repository, folio, user))
