"""Cálculo puro de los indicadores del servicio (S5-05, HU-09.1 y HU-09.2).

No conoce la base de datos ni HTTP: recibe las solicitudes ya medidas por el servicio
(con su tiempo efectivo y el tiempo comprometido por su acuerdo) y devuelve el
resumen o el contenido del CSV de exportación.
"""

import csv
import io
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

SIN_PRIORIDAD = "sin_prioridad"
SIN_CATEGORIA = "Sin categoría"

ENCABEZADO_CSV = (
    "Folio",
    "Título",
    "Categoría",
    "Prioridad",
    "Estatus",
    "Fecha de alta",
    "Primera respuesta",
    "Resuelta",
    "Cerrada",
    "Minutos de resolución",
    "Cumplió SLA",
)


@dataclass(frozen=True)
class SolicitudMedida:
    """Datos de una solicitud que intervienen en los indicadores."""

    folio: str
    titulo: str
    categoria: str | None
    prioridad: str | None
    estatus: str
    creada: datetime
    primera_respuesta: datetime | None
    resuelta: datetime | None
    cerrada: datetime | None
    minutos_resolucion: int | None
    # Tiempo de resolución comprometido por la versión del acuerdo; `None` sin acuerdo.
    minutos_comprometidos: int | None
    abierta: bool
    # Tiempo efectivo transcurrido (sin esperas) al momento del corte.
    minutos_efectivos: float = 0.0


@dataclass(frozen=True)
class ConteoDia:
    fecha: date
    total: int


@dataclass(frozen=True)
class ResumenIndicadores:
    desde: date
    hasta: date
    total: int
    por_estatus: dict[str, int] = field(default_factory=dict)
    por_prioridad: dict[str, int] = field(default_factory=dict)
    por_categoria: dict[str, int] = field(default_factory=dict)
    resueltas_con_sla: int = 0
    resueltas_en_tiempo: int = 0
    cumplimiento_sla: float = 0.0
    tiempo_medio_primera_respuesta_min: float = 0.0
    tiempo_medio_resolucion_min: float = 0.0
    abiertas_vencidas: int = 0
    por_dia: list[ConteoDia] = field(default_factory=list)


def _utc(valor: datetime) -> datetime:
    return valor.replace(tzinfo=UTC) if valor.tzinfo is None else valor.astimezone(UTC)


def _minutos(inicio: datetime, fin: datetime) -> float:
    return max((_utc(fin) - _utc(inicio)).total_seconds() / 60, 0.0)


def _promedio(valores: Sequence[float]) -> float:
    return round(sum(valores) / len(valores), 1) if valores else 0.0


def cumplio_sla(solicitud: SolicitudMedida) -> bool | None:
    """`True`/`False` si se resolvió y tiene acuerdo; `None` si no aplica."""
    if solicitud.minutos_comprometidos is None or solicitud.minutos_resolucion is None:
        return None
    return solicitud.minutos_resolucion <= solicitud.minutos_comprometidos


def esta_vencida(solicitud: SolicitudMedida) -> bool:
    """Abierta, con acuerdo, y su tiempo efectivo ya rebasó el comprometido."""
    return (
        solicitud.abierta
        and solicitud.minutos_comprometidos is not None
        and solicitud.minutos_efectivos > solicitud.minutos_comprometidos
    )


def resumir(solicitudes: Iterable[SolicitudMedida], desde: date, hasta: date) -> ResumenIndicadores:
    """Resumen del rango [`desde`, `hasta`]; un rango sin solicitudes da ceros."""
    lista = list(solicitudes)
    cumplimientos = [c for c in (cumplio_sla(s) for s in lista) if c is not None]
    en_tiempo = sum(1 for c in cumplimientos if c)
    primeras = [_minutos(s.creada, s.primera_respuesta) for s in lista if s.primera_respuesta]
    resoluciones = [float(s.minutos_resolucion) for s in lista if s.minutos_resolucion is not None]

    por_fecha = Counter(_utc(s.creada).date() for s in lista)
    dias = (hasta - desde).days + 1
    por_dia = [
        ConteoDia(fecha=dia, total=por_fecha.get(dia, 0))
        for dia in (desde + timedelta(days=i) for i in range(dias))
    ]

    return ResumenIndicadores(
        desde=desde,
        hasta=hasta,
        total=len(lista),
        por_estatus=dict(Counter(s.estatus for s in lista)),
        por_prioridad=dict(Counter(s.prioridad or SIN_PRIORIDAD for s in lista)),
        por_categoria=dict(Counter(s.categoria or SIN_CATEGORIA for s in lista)),
        resueltas_con_sla=len(cumplimientos),
        resueltas_en_tiempo=en_tiempo,
        cumplimiento_sla=round(100 * en_tiempo / len(cumplimientos), 1) if cumplimientos else 0.0,
        tiempo_medio_primera_respuesta_min=_promedio(primeras),
        tiempo_medio_resolucion_min=_promedio(resoluciones),
        abiertas_vencidas=sum(1 for s in lista if esta_vencida(s)),
        por_dia=por_dia,
    )


def _fecha(valor: datetime | None) -> str:
    return _utc(valor).strftime("%Y-%m-%d %H:%M") if valor else ""


def _si_no(valor: bool | None) -> str:
    if valor is None:
        return ""
    return "sí" if valor else "no"


def exportar_csv(solicitudes: Iterable[SolicitudMedida]) -> bytes:
    """CSV en UTF-8 con BOM (Excel reconoce los acentos), una fila por solicitud."""
    salida = io.StringIO()
    escritor = csv.writer(salida, lineterminator="\r\n")
    escritor.writerow(ENCABEZADO_CSV)
    for s in solicitudes:
        escritor.writerow(
            (
                s.folio,
                s.titulo,
                s.categoria or "",
                s.prioridad or "",
                s.estatus,
                _fecha(s.creada),
                _fecha(s.primera_respuesta),
                _fecha(s.resuelta),
                _fecha(s.cerrada),
                "" if s.minutos_resolucion is None else s.minutos_resolucion,
                _si_no(cumplio_sla(s)),
            )
        )
    return salida.getvalue().encode("utf-8-sig")
