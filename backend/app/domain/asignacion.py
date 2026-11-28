"""Reglas de la asignación de técnicos (S5-03, HU-03.1).

El puntaje de cada técnico candidato suma tres componentes:

* **Especialidad** (`PUNTOS_ESPECIALIDAD`): el técnico tiene una especialidad que cuelga
  de la categoría de la solicitud. Pesa más que los otros dos juntos, así que un técnico
  con la especialidad siempre queda por encima de uno sin ella.
* **Turno** (`PUNTOS_TURNO`): el turno del técnico está vigente a la hora actual.
* **Carga** (hasta `PUNTOS_CARGA_MAX`): menos solicitudes activas asignadas, más puntos.

Los técnicos inactivos no son candidatos. Estas reglas son puras: no consultan la base
de datos ni conocen el ORM.
"""

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.models.enums import RequestStatus

PUNTOS_ESPECIALIDAD = 100
PUNTOS_TURNO = 20
PUNTOS_CARGA_MAX = 10

MINUTOS_DIA = 24 * 60

# Una solicitud en estos estados ya no admite asignación (ni cuenta como carga).
ESTADOS_NO_ASIGNABLES: frozenset[RequestStatus] = frozenset(
    {RequestStatus.RESOLVED, RequestStatus.CLOSED, RequestStatus.CLOSED_UNVERIFIED}
)

# Estados que pasan a «Asignada» al asignar un técnico; los demás conservan su estado.
ESTADOS_QUE_PASAN_A_ASIGNADA: frozenset[RequestStatus] = frozenset(
    {RequestStatus.REGISTERED, RequestStatus.CLASSIFIED}
)


@dataclass(frozen=True, slots=True)
class TecnicoCandidato:
    """Lo que el motor necesita saber de un técnico para puntuarlo."""

    id: uuid.UUID
    nombre: str
    activo: bool
    categorias: frozenset[uuid.UUID] = field(default_factory=frozenset)
    turno: str | None = None
    turno_inicio: int | None = None  # minutos desde la medianoche
    turno_fin: int | None = None
    carga: int = 0
    carga_maxima: int | None = None  # `None`: sin tope configurado


@dataclass(frozen=True, slots=True)
class Componente:
    concepto: str
    puntos: int
    detalle: str


@dataclass(frozen=True, slots=True)
class Propuesta:
    technician_id: uuid.UUID
    nombre: str
    score: int
    carga: int
    desglose: tuple[Componente, ...]
    al_limite: bool = False  # ya tiene su carga máxima de solicitudes activas

    @property
    def score_breakdown(self) -> str:
        """Desglose legible, p. ej. «Especialidad +100 (…) · Turno +0 (…) · Carga +8 (…)»."""
        return " · ".join(f"{c.concepto} +{c.puntos} ({c.detalle})" for c in self.desglose)


_SEPARADOR_DESGLOSE = " · "
_COMPONENTE_TEXTO = re.compile(r"^(?P<concepto>.+?) \+(?P<puntos>\d+) \((?P<detalle>.*)\)$")


def desglose_desde_texto(texto: str | None) -> tuple[Componente, ...]:
    """Reconstruye los componentes a partir de `Propuesta.score_breakdown`.

    La asignación guarda el desglose como texto («Especialidad +100 (…) · Turno +0 (…)»).
    Si el texto está vacío o alguna parte no tiene ese formato, devuelve `()` para que la
    interfaz muestre el texto tal cual en lugar de un desglose a medias.
    """
    if not texto or not texto.strip():
        return ()
    componentes: list[Componente] = []
    for parte in texto.split(_SEPARADOR_DESGLOSE):
        coincidencia = _COMPONENTE_TEXTO.match(parte.strip())
        if coincidencia is None:
            return ()
        componentes.append(
            Componente(
                coincidencia["concepto"],
                int(coincidencia["puntos"]),
                coincidencia["detalle"],
            )
        )
    return tuple(componentes)


def puede_asignarse(status: RequestStatus) -> bool:
    return status not in ESTADOS_NO_ASIGNABLES


def estado_al_asignar(status: RequestStatus) -> RequestStatus:
    """Estado con el que queda la solicitud tras asignarle un técnico."""
    if status in ESTADOS_QUE_PASAN_A_ASIGNADA:
        return RequestStatus.ASSIGNED
    return status


def turno_vigente(inicio: int | None, fin: int | None, minuto_del_dia: int) -> bool:
    """`True` si el minuto cae en el turno [inicio, fin); admite turnos que cruzan la
    medianoche (inicio mayor que fin)."""
    if inicio is None or fin is None:
        return False
    minuto = minuto_del_dia % MINUTOS_DIA
    if inicio <= fin:
        return inicio <= minuto < fin
    return minuto >= inicio or minuto < fin


def en_carga_maxima(carga: int, carga_maxima: int | None) -> bool:
    """`True` si el técnico ya tiene tantas solicitudes activas como su tope.

    Sin tope (`None`) nunca está al límite. Un tope de 0 lo deja siempre al límite.
    """
    return carga_maxima is not None and carga >= carga_maxima


def puntos_carga(carga: int) -> int:
    return max(0, PUNTOS_CARGA_MAX - max(0, carga))


def puntuar(
    tecnico: TecnicoCandidato, categoria_id: uuid.UUID | None, minuto_del_dia: int
) -> Propuesta:
    """Puntaje de un técnico para una solicitud de la categoría indicada."""
    con_especialidad = categoria_id is not None and categoria_id in tecnico.categorias
    en_turno = turno_vigente(tecnico.turno_inicio, tecnico.turno_fin, minuto_del_dia)
    desglose = (
        Componente(
            "Especialidad",
            PUNTOS_ESPECIALIDAD if con_especialidad else 0,
            "atiende la categoría" if con_especialidad else "sin especialidad de la categoría",
        ),
        Componente(
            "Turno",
            PUNTOS_TURNO if en_turno else 0,
            f"{tecnico.turno or 'sin turno'}: {'en turno' if en_turno else 'fuera de turno'}",
        ),
        Componente(
            "Carga",
            puntos_carga(tecnico.carga),
            f"{tecnico.carga} solicitud{'es' if tecnico.carga != 1 else ''} activa"
            f"{'s' if tecnico.carga != 1 else ''}",
        ),
    )
    return Propuesta(
        technician_id=tecnico.id,
        nombre=tecnico.nombre,
        score=sum(c.puntos for c in desglose),
        carga=tecnico.carga,
        desglose=desglose,
        al_limite=en_carga_maxima(tecnico.carga, tecnico.carga_maxima),
    )


def proponer(
    tecnicos: Iterable[TecnicoCandidato], categoria_id: uuid.UUID | None, minuto_del_dia: int
) -> list[Propuesta]:
    """Candidatos activos ordenados del mejor al peor puntaje.

    Empates: primero el de menor carga y luego por nombre, para que el orden sea estable.
    """
    propuestas = [puntuar(t, categoria_id, minuto_del_dia) for t in tecnicos if t.activo]
    return sorted(propuestas, key=lambda p: (-p.score, p.carga, p.nombre, str(p.technician_id)))


def con_capacidad(propuestas: Iterable[Propuesta], es_p1: bool) -> list[Propuesta]:
    """Candidatos que pueden recibir la solicitud automáticamente (S5-14, HU-03.3).

    * **P1**: se ignora la carga máxima; cualquier candidato activo puede recibirla.
    * **Demás prioridades**: se descartan los técnicos que ya están en su carga máxima.
      Si no queda ninguno, la solicitud espera en la cola general (sin técnico).

    Conserva el orden recibido. La asignación manual no usa esta regla.
    """
    propuestas = list(propuestas)
    if es_p1:
        return propuestas
    return [p for p in propuestas if not p.al_limite]
