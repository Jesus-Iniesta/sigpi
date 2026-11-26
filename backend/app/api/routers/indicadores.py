"""Indicadores del servicio y exportación a CSV (S5-05, HU-09.1 y HU-09.2)."""

from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.core.permissions import Permission
from app.db.session import get_session
from app.repositories.indicador_repository import IndicadorRepository
from app.schemas.indicadores import ResumenIndicadoresRead
from app.services.indicador_service import IndicadorService

router = APIRouter(
    prefix="/indicadores",
    tags=["indicadores"],
    dependencies=[Depends(require_permission(Permission.REPORTS_READ))],
)


def get_indicador_service(session: AsyncSession = Depends(get_session)) -> IndicadorService:
    return IndicadorService(IndicadorRepository(session))


@router.get("/resumen", response_model=ResumenIndicadoresRead)
async def resumen(
    desde: date | None = None,
    hasta: date | None = None,
    service: IndicadorService = Depends(get_indicador_service),
):
    """Resumen del rango; por omisión, los últimos 30 días."""
    return await service.resumen(desde, hasta)


@router.get("/exportar.csv", response_class=Response)
async def exportar(
    desde: date | None = None,
    hasta: date | None = None,
    service: IndicadorService = Depends(get_indicador_service),
) -> Response:
    """Una fila por solicitud del rango, en CSV UTF-8 con BOM para Excel."""
    inicio, fin, contenido = await service.exportar(desde, hasta)
    nombre = f"indicadores_{inicio.isoformat()}_{fin.isoformat()}.csv"
    return Response(
        content=contenido,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
