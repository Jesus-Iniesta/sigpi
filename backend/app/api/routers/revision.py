import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AuditContext, get_audit_context, require_permission
from app.core.permissions import Permission
from app.db.session import get_session
from app.models.identity import User
from app.schemas.revision import RevisionInput, RevisionItem, RevisionResult
from app.services.revision_service import RevisionService

router = APIRouter(prefix="/revision", tags=["revision"])


def get_revision_service(session: AsyncSession = Depends(get_session)) -> RevisionService:
    return RevisionService(session)


@router.get("/cola", response_model=list[RevisionItem])
async def revision_queue(
    _: User = Depends(require_permission(Permission.CLASSIFICATION_REVIEW)),
    service: RevisionService = Depends(get_revision_service),
) -> list[RevisionItem]:
    """Clasificaciones de baja confianza que esperan revisión, de la más antigua a la más
    reciente."""
    return await service.cola()


@router.post("/{result_id}/correccion", response_model=RevisionResult)
async def corregir_clasificacion(
    result_id: uuid.UUID,
    datos: RevisionInput,
    _: User = Depends(require_permission(Permission.CLASSIFICATION_REVIEW)),
    contexto: AuditContext = Depends(get_audit_context),
    service: RevisionService = Depends(get_revision_service),
) -> RevisionResult:
    """Guarda la revisión de una clasificación: aplica las etiquetas, recalcula la
    prioridad, deja la solicitud «Clasificada» y registra la corrección como ejemplo."""
    return await service.corregir(result_id, datos, contexto)
