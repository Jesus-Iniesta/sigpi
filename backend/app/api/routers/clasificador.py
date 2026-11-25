"""Administración del clasificador (S5-06, HU-02.2, HU-12.1, HU-12.2).

Solo valida y delega en `ClasificadorAdminService`. Todo exige `CLASSIFICATION_MANAGE`,
que solo tiene `administrator`.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AuditContext, get_audit_context, require_permission
from app.core.permissions import Permission
from app.db.session import get_session
from app.schemas.clasificador import (
    EstadoClasificador,
    ReentrenamientoResult,
    UmbralInput,
    UmbralResult,
)
from app.services.clasificador_admin_service import ClasificadorAdminService

router = APIRouter(
    prefix="/clasificador",
    tags=["clasificador"],
    dependencies=[Depends(require_permission(Permission.CLASSIFICATION_MANAGE))],
)


def get_clasificador_admin_service(
    session: AsyncSession = Depends(get_session),
) -> ClasificadorAdminService:
    return ClasificadorAdminService(session)


@router.get("/estado", response_model=EstadoClasificador)
async def estado_clasificador(
    service: ClasificadorAdminService = Depends(get_clasificador_admin_service),
) -> EstadoClasificador:
    """Versión, umbral, ejemplos y exactitud del modelo vigente, correcciones pendientes de
    incorporar y proporción reciente de solicitudes enviadas a «Por revisar»."""
    return await service.estado()


@router.put("/umbral", response_model=UmbralResult)
async def cambiar_umbral(
    datos: UmbralInput,
    contexto: AuditContext = Depends(get_audit_context),
    service: ClasificadorAdminService = Depends(get_clasificador_admin_service),
) -> UmbralResult:
    """Cambia el umbral de confianza (0.50 a 0.95) sin reiniciar el servicio."""
    return await service.cambiar_umbral(datos.umbral, contexto)


@router.post("/reentrenar", response_model=ReentrenamientoResult)
async def reentrenar_clasificador(
    contexto: AuditContext = Depends(get_audit_context),
    service: ClasificadorAdminService = Depends(get_clasificador_admin_service),
) -> ReentrenamientoResult:
    """Entrena una versión nueva con el conjunto de datos más reciente y las correcciones;
    la activa solo si su exactitud no empeora."""
    return await service.reentrenar(contexto)
