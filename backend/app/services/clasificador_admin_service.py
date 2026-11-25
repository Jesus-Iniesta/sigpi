"""Administración del clasificador (S5-06, HU-02.2, HU-12.1, HU-12.2).

* Umbral de confianza (RN-06) configurable en caliente en `app_settings`.
* Estado del modelo vigente: versión, umbral, ejemplos, exactitud y uso de la revisión.
* Reentrenamiento con el conjunto de datos más reciente más las correcciones de las
  personas revisoras. La versión nueva queda vigente solo si su exactitud con validación
  cruzada no empeora respecto de la anterior.

Cada escritura se audita con `AuditContext` y confirma su transacción (regla 7).
"""

import asyncio
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError
from app.core.logging import get_logger, log_event
from app.domain.auditoria import AuditContext
from app.integrations.clasificador_client import (
    ClasificadorBayes,
    Ejemplo,
    cargar_ejemplos,
    obtener_clasificador,
    ruta_dataset,
    ruta_dataset_mas_reciente,
    validacion_cruzada,
)
from app.models.classification import ClassifierModel
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.clasificador_admin_repository import ClasificadorAdminRepository
from app.repositories.correccion_repository import CorreccionRepository
from app.schemas.clasificador import (
    UMBRAL_MAXIMO,
    UMBRAL_MINIMO,
    EstadoClasificador,
    ReentrenamientoResult,
    UmbralResult,
)
from app.services.auditoria_service import AuditoriaService
from app.services.clasificacion_service import CLAVE_UMBRAL, ClasificacionService
from app.services.solicitud_service import ACCION_CLASIFICACION

logger = get_logger("clasificacion")

ACCION_UMBRAL = "clasificador.umbral_actualizado"
ACCION_REENTRENADO = "clasificador.reentrenado"
ENTIDAD_AJUSTE = "app_setting"
ENTIDAD_MODELO = "classifier_model"
DIAS_RECIENTES = 30
_DECIMALES = 4  # `Numeric(5, 4)` en `accuracy`
_ERRORES_DATASET = (OSError, ValueError, KeyError)


class UmbralFueraDeRangoError(BusinessRuleError):
    default_message = f"El umbral debe estar entre {UMBRAL_MINIMO:.2f} y {UMBRAL_MAXIMO:.2f}."


def _numero_de_version(version: str) -> int:
    coincide = re.fullmatch(r"nb-v(\d+)", version)
    return int(coincide.group(1)) if coincide else 1


def _contar_ejemplos_base() -> int:
    try:
        return len(cargar_ejemplos(ruta_dataset()))
    except _ERRORES_DATASET:
        return 0


def _entrenar(ejemplos: list[Ejemplo], version: str) -> tuple[ClasificadorBayes, float]:
    """Entrena el modelo y mide su exactitud de categoría con validación cruzada."""
    modelo = ClasificadorBayes(ejemplos, medir_exactitud=False, version=version)
    return modelo, round(validacion_cruzada(ejemplos)["categoria"], _DECIMALES)


class ClasificadorAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = ClasificadorAdminRepository(session)
        self._correcciones = CorreccionRepository(session)
        self._clasificacion = ClasificacionService(session)
        self._auditoria = AuditoriaService(AuditoriaRepository(session))

    async def estado(self, ahora: datetime | None = None) -> EstadoClasificador:
        ahora = ahora or datetime.now(UTC)
        activo = await self._repository.modelo_activo()
        if activo is not None:
            version, exactitud = activo.version, float(activo.accuracy)
            ejemplos, entrenado_en = activo.examples, activo.created_at
        else:
            base = obtener_clasificador()
            version, exactitud = base.version, base.exactitud
            ejemplos, entrenado_en = _contar_ejemplos_base(), None
        total, a_revision = await self._repository.decisiones_de_clasificacion(
            ACCION_CLASIFICACION, ahora - timedelta(days=DIAS_RECIENTES)
        )
        return EstadoClasificador(
            version=version,
            umbral=await self._clasificacion.umbral_vigente(),
            ejemplos=ejemplos,
            exactitud=None if exactitud is None else round(exactitud, _DECIMALES),
            correcciones_pendientes=await self._repository.contar_correcciones_desde(entrenado_en),
            proporcion_por_revisar=round(a_revision / total, _DECIMALES) if total else None,
            dias_recientes=DIAS_RECIENTES,
            entrenado_en=entrenado_en,
        )

    async def cambiar_umbral(self, umbral: float, contexto: AuditContext) -> UmbralResult:
        """Guarda el umbral nuevo, lo audita y confirma la transacción."""
        if not UMBRAL_MINIMO <= umbral <= UMBRAL_MAXIMO:
            raise UmbralFueraDeRangoError()
        anterior = await self._clasificacion.umbral_vigente()
        await self._repository.guardar_ajuste(CLAVE_UMBRAL, str(umbral), contexto.actor_id)
        await self._auditoria.registrar(
            contexto,
            action=ACCION_UMBRAL,
            entity_type=ENTIDAD_AJUSTE,
            entity_id=CLAVE_UMBRAL,
            old_values={"umbral": anterior},
            new_values={"umbral": umbral},
        )
        await self._session.commit()
        log_event(logger, "clasificador.umbral_actualizado", anterior=anterior, nuevo=umbral)
        return UmbralResult(umbral_anterior=anterior, umbral=umbral)

    async def reentrenar(self, contexto: AuditContext) -> ReentrenamientoResult:
        """Entrena una versión nueva, la guarda y la activa solo si no empeora."""
        ejemplos = cargar_ejemplos(ruta_dataset_mas_reciente())
        corregidos = await self._correcciones.ejemplos_para_reentrenamiento()
        ejemplos += [
            Ejemplo(
                texto=f"{c.titulo}. {c.descripcion}",
                categoria=c.categoria,
                urgencia=c.urgencia,
                impacto=c.impacto,
            )
            for c in corregidos
        ]

        activo = await self._repository.modelo_activo()
        if activo is not None:
            version_anterior, exactitud_anterior = activo.version, float(activo.accuracy)
        else:
            base = obtener_clasificador()
            version_anterior, exactitud_anterior = base.version, base.exactitud

        numeros = [_numero_de_version(v) for v in await self._repository.versiones()]
        version = f"nb-v{max([1, *numeros]) + 1}"
        # Entrenar y validar es CPU puro: fuera del bucle de eventos.
        modelo, exactitud = await asyncio.to_thread(_entrenar, ejemplos, version)
        activar = exactitud_anterior is None or exactitud >= round(exactitud_anterior, _DECIMALES)

        fila = await self._repository.agregar_modelo(
            ClassifierModel(
                version=version,
                accuracy=exactitud,
                examples=len(ejemplos),
                parameters=modelo.parametros(),
            ),
            activar=activar,
        )
        resultado = ReentrenamientoResult(
            version=version,
            exactitud=exactitud,
            ejemplos=len(ejemplos),
            correcciones_incorporadas=len(corregidos),
            version_anterior=version_anterior,
            exactitud_anterior=exactitud_anterior,
            activado=activar,
            mensaje=_mensaje(version, exactitud, version_anterior, exactitud_anterior, activar),
        )
        await self._auditoria.registrar(
            contexto,
            action=ACCION_REENTRENADO,
            entity_type=ENTIDAD_MODELO,
            entity_id=fila.id,
            new_values=resultado.model_dump(exclude={"mensaje"}),
        )
        await self._session.commit()
        log_event(
            logger,
            "clasificador.reentrenado",
            version=version,
            exactitud=exactitud,
            anterior=exactitud_anterior,
            activado=activar,
        )
        return resultado


def _mensaje(
    version: str,
    exactitud: float,
    version_anterior: str,
    exactitud_anterior: float | None,
    activado: bool,
) -> str:
    comparacion = f"{version}: {exactitud:.2%} frente a {version_anterior}: " + (
        "sin medir" if exactitud_anterior is None else f"{exactitud_anterior:.2%}"
    )
    if activado:
        return f"La versión {version} quedó vigente ({comparacion})."
    return (
        f"La versión {version} se guardó pero no se activó porque su exactitud empeora "
        f"({comparacion}). Sigue vigente {version_anterior}."
    )
