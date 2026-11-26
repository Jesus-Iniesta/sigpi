"""Indicadores del servicio y exportación a CSV (S5-05, HU-09.1 y HU-09.2).

Orquesta la consulta del rango, mide cada solicitud (tiempo efectivo sin esperas y
tiempo comprometido por su acuerdo) y delega el cálculo al dominio. Solo lee.
"""

from datetime import UTC, date, datetime, time, timedelta

from app.core.exceptions import BusinessRuleError
from app.domain.indicadores import ResumenIndicadores, SolicitudMedida, exportar_csv, resumir
from app.models.request import Request
from app.repositories.indicador_repository import IndicadorRepository
from app.services.sla_clock_service import minutos_efectivos
from app.services.sla_monitor_service import ESTADOS_CERRADOS

DIAS_POR_OMISION = 30


class RangoFechasInvalidoError(BusinessRuleError):
    default_message = "La fecha «desde» no puede ser posterior a la fecha «hasta»."


def _hoy() -> date:
    return datetime.now(UTC).date()


def resolver_rango(
    desde: date | None, hasta: date | None, hoy: date | None = None
) -> tuple[date, date]:
    """Completa el rango (por omisión, los últimos 30 días) y valida su orden."""
    fin = hasta or hoy or _hoy()
    inicio = desde or fin - timedelta(days=DIAS_POR_OMISION - 1)
    if inicio > fin:
        raise RangoFechasInvalidoError()
    return inicio, fin


def _medir(request: Request, ahora: datetime) -> SolicitudMedida:
    version = request.service_level_version
    abierta = request.status not in ESTADOS_CERRADOS
    return SolicitudMedida(
        folio=request.folio,
        titulo=request.title,
        categoria=request.category.name if request.category else None,
        prioridad=str(request.priority) if request.priority else None,
        estatus=str(request.status),
        creada=request.created_at,
        primera_respuesta=request.first_response_at,
        resuelta=request.resolved_at,
        cerrada=request.closed_at,
        minutos_resolucion=request.resolution_minutes,
        minutos_comprometidos=version.resolution_minutes if version else None,
        abierta=abierta,
        minutos_efectivos=minutos_efectivos(request, ahora) if abierta else 0.0,
    )


class IndicadorService:
    def __init__(self, repository: IndicadorRepository) -> None:
        self._repository = repository

    async def _medidas(
        self, inicio: date, fin: date, ahora: datetime | None
    ) -> list[SolicitudMedida]:
        corte = ahora or datetime.now(UTC)
        solicitudes = await self._repository.solicitudes_en_rango(
            datetime.combine(inicio, time.min, tzinfo=UTC),
            datetime.combine(fin + timedelta(days=1), time.min, tzinfo=UTC),
        )
        return [_medir(r, corte) for r in solicitudes]

    async def resumen(
        self,
        desde: date | None = None,
        hasta: date | None = None,
        ahora: datetime | None = None,
    ) -> ResumenIndicadores:
        inicio, fin = resolver_rango(desde, hasta, ahora.date() if ahora else None)
        return resumir(await self._medidas(inicio, fin, ahora), inicio, fin)

    async def exportar(
        self,
        desde: date | None = None,
        hasta: date | None = None,
        ahora: datetime | None = None,
    ) -> tuple[date, date, bytes]:
        inicio, fin = resolver_rango(desde, hasta, ahora.date() if ahora else None)
        return inicio, fin, exportar_csv(await self._medidas(inicio, fin, ahora))
