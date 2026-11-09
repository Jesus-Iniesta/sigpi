from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.core.permissions import Permission
from app.db.session import get_session
from app.models.identity import User
from app.schemas.revision import RevisionItem
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
