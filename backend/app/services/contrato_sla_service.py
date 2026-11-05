"""Contrato simulado del acuerdo de nivel de servicio en PDF (COR-06A, HU-08.1).

Arma un documento con fines académicos a partir de la versión vigente de un acuerdo:
datos del acuerdo, partes, descripción del servicio, tabla de compromisos por
prioridad, cláusulas generales y un pie con folio y leyenda de no validez oficial.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.exceptions import BusinessRuleError
from app.domain.sla_options import service_description
from app.models.enums import Priority
from app.repositories.sla_repository import SlaRepository
from app.services.sla_service import SlaNotFoundError, as_utc

# Toluca y la Ciudad de México usan UTC-6 todo el año desde 2022 (sin horario de verano).
# Se usa un desfase fijo para no depender de la base de zonas horarias del sistema.
HORA_CENTRO_MEXICO = timezone(timedelta(hours=-6), "UTC-6")

PRESTADOR = "Departamento de Tecnologías de la Información y Comunicación de la FI (DTIC-FI)"
TODAS_LAS_CATEGORIAS = "Aplica a todas las categorías"
SIN_COMPROMISO = "No definido"


class SlaWithoutCurrentVersionError(BusinessRuleError):
    """El acuerdo no tiene una versión vigente para generar el contrato."""

    code = "sla_without_current_version"


@dataclass(frozen=True)
class Compromiso:
    priority: Priority
    first_response_minutes: int | None
    resolution_minutes: int | None


@dataclass(frozen=True)
class DatosContrato:
    agreement_id: uuid.UUID
    nombre: str
    categoria: str
    version: int
    vigente_desde: datetime
    compromisos: list[Compromiso]
    usuario_nombre: str
    usuario_correo: str
    generado_en: datetime

    @property
    def folio(self) -> str:
        return folio_contrato(self.agreement_id, self.version)

    @property
    def nombre_archivo(self) -> str:
        return f"contrato-{slugify(self.nombre)}-v{self.version}.pdf"


@dataclass(frozen=True)
class ContratoPdf:
    nombre_archivo: str
    contenido: bytes


# --- utilidades de formato ---------------------------------------------------
def folio_contrato(agreement_id: uuid.UUID, version: int) -> str:
    """Folio `SLA-<id corto>-v<versión>`; el id corto son los primeros 8 caracteres."""
    return f"SLA-{agreement_id.hex[:8].upper()}-v{version}"


def slugify(texto: str) -> str:
    """Convierte un nombre en un fragmento ASCII seguro para el nombre de archivo."""
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-")
    return slug or "acuerdo"


def duracion_legible(minutos: int | None) -> str:
    """`90` → «1 h 30 min»; `45` → «45 min»; `120` → «2 h»."""
    if minutos is None:
        return SIN_COMPROMISO
    horas, resto = divmod(minutos, 60)
    if horas and resto:
        return f"{horas} h {resto} min"
    if horas:
        return f"{horas} h"
    return f"{resto} min"


def _fecha(valor: datetime) -> str:
    return as_utc(valor).astimezone(HORA_CENTRO_MEXICO).strftime("%d/%m/%Y")


def _fecha_hora(valor: datetime) -> str:
    return as_utc(valor).astimezone(HORA_CENTRO_MEXICO).strftime("%d/%m/%Y %H:%M (UTC-6)")


# --- caso de uso -------------------------------------------------------------
class ContratoSlaService:
    def __init__(self, repository: SlaRepository) -> None:
        self._repository = repository

    async def generar(
        self,
        agreement_id: uuid.UUID,
        *,
        usuario_nombre: str,
        usuario_correo: str,
        ahora: datetime | None = None,
    ) -> ContratoPdf:
        datos = await self.reunir_datos(
            agreement_id,
            usuario_nombre=usuario_nombre,
            usuario_correo=usuario_correo,
            ahora=ahora,
        )
        return ContratoPdf(nombre_archivo=datos.nombre_archivo, contenido=render_contrato(datos))

    async def reunir_datos(
        self,
        agreement_id: uuid.UUID,
        *,
        usuario_nombre: str,
        usuario_correo: str,
        ahora: datetime | None = None,
    ) -> DatosContrato:
        momento = as_utc(ahora) if ahora is not None else datetime.now(UTC)
        agreement = await self._repository.get_agreement(agreement_id)
        if agreement is None:
            raise SlaNotFoundError(f"No existe el acuerdo {agreement_id}.")

        vigentes = {}
        for priority in Priority:
            version = await self._repository.find_effective(agreement_id, priority.value, momento)
            if version is not None:
                vigentes[priority] = version
        if not vigentes:
            raise SlaWithoutCurrentVersionError(
                "El acuerdo no tiene una versión vigente; publica una antes de generar el contrato."
            )

        # La versión vigente del acuerdo es la más reciente entre las prioridades vigentes.
        actual = max(vigentes.values(), key=lambda v: (v.version, as_utc(v.valid_from)))

        if agreement.is_default or agreement.category_id is None:
            categoria = TODAS_LAS_CATEGORIAS
        else:
            categoria = (
                await self._repository.get_category_name(agreement.category_id)
                or "Categoría no disponible"
            )

        compromisos = [
            Compromiso(
                priority=priority,
                first_response_minutes=(
                    vigentes[priority].first_response_minutes if priority in vigentes else None
                ),
                resolution_minutes=(
                    vigentes[priority].resolution_minutes if priority in vigentes else None
                ),
            )
            for priority in Priority
        ]
        return DatosContrato(
            agreement_id=agreement.id,
            nombre=agreement.name,
            categoria=categoria,
            version=actual.version,
            vigente_desde=actual.valid_from,
            compromisos=compromisos,
            usuario_nombre=usuario_nombre,
            usuario_correo=usuario_correo,
            generado_en=momento,
        )


# --- render del PDF ----------------------------------------------------------
CLAUSULAS = (
    (
        "Suspensión del reloj. El tiempo comprometido se suspende mientras la atención dependa "
        "de causas ajenas al prestador, como la espera de información o de disponibilidad del "
        "usuario, o la intervención de un proveedor externo (HU-04.2). El reloj se reanuda al "
        "desaparecer la causa."
    ),
    (
        "Confirmación de la solución. Una solicitud se considera atendida cuando el prestador "
        "registra la solución y el usuario la confirma. Si el usuario no está conforme, la "
        "solicitud se reabre y el compromiso de resolución continúa."
    ),
    (
        "Vigencia. Este acuerdo permanece vigente desde su fecha de entrada en vigor y hasta "
        "que se publique una nueva versión, que sustituye a la presente sin efectos retroactivos "
        "sobre las solicitudes ya registradas."
    ),
)


def render_contrato(datos: DatosContrato) -> bytes:
    """Genera el PDF del contrato simulado y devuelve sus bytes."""
    estilos = getSampleStyleSheet()
    normal = estilos["BodyText"]
    titulo = ParagraphStyle("Titulo", parent=estilos["Title"], fontSize=15, spaceAfter=4)
    subtitulo = ParagraphStyle("Subtitulo", parent=normal, alignment=TA_CENTER, fontSize=10)
    seccion = ParagraphStyle("Seccion", parent=estilos["Heading3"], spaceBefore=10)
    pie = ParagraphStyle(
        "Pie", parent=normal, fontSize=8, textColor=colors.grey, alignment=TA_CENTER
    )

    def p(texto: str, estilo: ParagraphStyle = normal) -> Paragraph:
        return Paragraph(escape(texto), estilo)

    def pie_de_pagina(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(
            LETTER[0] / 2,
            1.2 * cm,
            f"Folio {datos.folio} · Generado el {_fecha_hora(datos.generado_en)} · "
            "Documento sin validez oficial",
        )
        canvas.restoreState()

    elementos = [
        p("UAEMéx · Facultad de Ingeniería", subtitulo),
        p("Contrato de nivel de servicio", titulo),
        p("(documento simulado con fines académicos)", subtitulo),
        Spacer(1, 0.4 * cm),
        p("Datos del acuerdo", seccion),
        _tabla_datos(
            [
                ("Acuerdo (tipo de servicio)", datos.nombre),
                ("Categoría", datos.categoria),
                ("Versión vigente", str(datos.version)),
                ("Fecha de entrada en vigor", _fecha(datos.vigente_desde)),
                ("Folio", datos.folio),
            ],
            normal,
        ),
        p("Partes", seccion),
        _tabla_datos(
            [
                ("Prestador", PRESTADOR),
                ("Usuario", "Comunidad universitaria de la Facultad de Ingeniería"),
                ("Descargado por", datos.usuario_nombre),
                ("Correo", datos.usuario_correo),
            ],
            normal,
        ),
        p("Descripción del servicio", seccion),
        p(service_description(datos.nombre)),
        p("Compromisos de atención", seccion),
        _tabla_compromisos(datos.compromisos, normal),
        p("Cláusulas generales", seccion),
    ]
    for numero, clausula in enumerate(CLAUSULAS, start=1):
        elementos.append(p(f"{numero}. {clausula}"))
    elementos += [
        Spacer(1, 0.6 * cm),
        p(
            f"Folio {datos.folio} · Generado el {_fecha_hora(datos.generado_en)}. "
            "Documento sin validez oficial.",
            pie,
        ),
    ]

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        title=f"Contrato de nivel de servicio {datos.folio}",
        author="SIGPI · DTIC-FI",
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    documento.build(elementos, onFirstPage=pie_de_pagina, onLaterPages=pie_de_pagina)
    return buffer.getvalue()


def _tabla_datos(filas: list[tuple[str, str]], estilo: ParagraphStyle) -> Table:
    tabla = Table(
        [
            [Paragraph(f"<b>{escape(k)}</b>", estilo), Paragraph(escape(v), estilo)]
            for k, v in filas
        ],
        colWidths=[5 * cm, 12 * cm],
    )
    tabla.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ]
        )
    )
    return tabla


def _tabla_compromisos(compromisos: list[Compromiso], estilo: ParagraphStyle) -> Table:
    filas = [["Prioridad", "Primera respuesta", "Resolución"]]
    filas += [
        [
            c.priority.value,
            duracion_legible(c.first_response_minutes),
            duracion_legible(c.resolution_minutes),
        ]
        for c in compromisos
    ]
    tabla = Table(filas, colWidths=[4 * cm, 6.5 * cm, 6.5 * cm])
    tabla.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF4")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    return tabla
