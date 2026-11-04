"""Consulta de solo lectura de la bitácora de auditoría (S2-08, HU-10.3).

No hay endpoints de modificación ni de borrado: la bitácora es inalterable.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.core.permissions import Permission
from app.db.session import get_session
from app.repositories.auditoria_repository import AuditoriaRepository
from app.schemas.auditoria import AuditoriaRead
from app.services.auditoria_service import AuditoriaService

router = APIRouter(prefix="/auditoria", tags=["auditoria"])


def get_auditoria_service(session: AsyncSession = Depends(get_session)) -> AuditoriaService:
    return AuditoriaService(AuditoriaRepository(session))


@router.get(
    "",
    response_model=list[AuditoriaRead],
    dependencies=[Depends(require_permission(Permission.AUDIT_READ))],
)
async def list_audit_entries(
    entity_type: str | None = None,
    entity_id: str | None = None,
    service: AuditoriaService = Depends(get_auditoria_service),
):
    """Registros en orden cronológico, filtrados opcionalmente por entidad."""
    return await service.consultar(entity_type=entity_type, entity_id=entity_id)
