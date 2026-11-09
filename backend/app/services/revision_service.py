"""Umbral de confianza y cola de revisión de clasificaciones (S4-14, HU-02.2 AC1).

Una clasificación con confianza menor que el umbral (RN-06) deja la solicitud «Por
revisar» (`pending_review`); si alcanza el umbral queda «Clasificada». El umbral se lee
de `settings.classification_confidence_threshold`; que el administrador lo cambie desde
la interfaz queda fuera del Sprint 4.

La corrección de una clasificación (S4-16, HU-02.2 AC2) aplica las etiquetas de la
persona revisora, recalcula la prioridad (RN-05), deja la solicitud «Clasificada» y
guarda la corrección como ejemplo para reentrenar el modelo, todo en una transacción.
Con la prioridad nueva se asigna la versión vigente del acuerdo de nivel de servicio.
"""

import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.domain.auditoria import AuditContext
from app.domain.clasificacion import requiere_revision
from app.models.classification import ClassificationCorrection
from app.models.enums import RequestStatus
from app.models.request import RequestLog
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.correccion_repository import CorreccionRepository
from app.repositories.revision_repository import RevisionRepository
from app.repositories.sla_repository import SlaRepository
from app.schemas.revision import RevisionInput, RevisionItem, RevisionResult
from app.services.auditoria_service import AuditoriaService
from app.services.prioridad_service import PrioridadService
from app.services.sla_service import SlaService

ACCION_CORREGIDA = "clasificacion.corregida"
ENTIDAD_SOLICITUD = "service_request"
_CAMPOS_AUDITADOS = (
    "status",
    "category_id",
    "urgency",
    "impact",
    "priority",
    "service_level_version_id",
)


class _ConConfianza(Protocol):
    confidence: float


def decidir_estatus(resultado: _ConConfianza, umbral: float | None = None) -> RequestStatus:
    """Estatus que corresponde a una solicitud según la confianza de su clasificación."""
    limite = settings.classification_confidence_threshold if umbral is None else umbral
    if requiere_revision(resultado.confidence, limite):
        return RequestStatus.PENDING_REVIEW
    return RequestStatus.CLASSIFIED


class RevisionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = RevisionRepository(session)
        self._correcciones = CorreccionRepository(session)
        self._auditoria = AuditoriaService(AuditoriaRepository(session))
        self._prioridad = PrioridadService()
        self._sla = SlaService(SlaRepository(session), self._auditoria)

    async def cola(self) -> list[RevisionItem]:
        """Solicitudes «Por revisar» con su último resultado, de la más antigua a la más
        reciente. Una solicitud sin ningún resultado de clasificación no se incluye."""
        solicitudes = await self._repository.solicitudes_por_revisar()
        resultados = await self._repository.ultimos_resultados([s.id for s in solicitudes])
        return [
            RevisionItem.from_models(solicitud, resultados[solicitud.id])
            for solicitud in solicitudes
            if solicitud.id in resultados
        ]

    async def corregir(
        self,
        result_id: uuid.UUID,
        datos: RevisionInput,
        contexto: AuditContext,
    ) -> RevisionResult:
        """Aplica la corrección de la persona revisora y confirma la transacción.

        Solo se corrige un resultado cuya solicitud sigue «Por revisar» y que no tiene ya
        una corrección; si no, responde con conflicto (409).
        """
        resultado = await self._correcciones.get_resultado(result_id)
        if resultado is None:
            raise NotFoundError("El resultado de clasificación no existe.")
        solicitud = resultado.request
        if solicitud.status != RequestStatus.PENDING_REVIEW or (
            await self._correcciones.existe_para(result_id)
        ):
            raise ConflictError("La clasificación ya no está «Por revisar».")
        categoria = await self._correcciones.get_categoria(datos.category_id)
        if categoria is None or not categoria.is_active:
            raise BusinessRuleError("La categoría elegida no existe o está inactiva.")
        if contexto.actor_id is None:
            raise BusinessRuleError("No se identificó a la persona que corrige.")

        antes = {campo: getattr(solicitud, campo) for campo in _CAMPOS_AUDITADOS}
        solicitud.category_id = datos.category_id
        solicitud.urgency = datos.urgency
        solicitud.impact = datos.impact
        self._prioridad.aplicar(solicitud)
        solicitud.status = RequestStatus.CLASSIFIED

        await self._correcciones.add(
            ClassificationCorrection(
                result_id=resultado.id,
                corrected_by_id=contexto.actor_id,
                corrected_category_id=datos.category_id,
                corrected_urgency=datos.urgency,
                corrected_impact=datos.impact,
                justification=datos.justification,
            )
        )
        self._session.add(
            RequestLog(
                request_id=solicitud.id,
                author_id=contexto.actor_id,
                previous_status=RequestStatus.PENDING_REVIEW,
                new_status=RequestStatus.CLASSIFIED,
                action="Clasificación corregida",
                notes=datos.justification,
            )
        )
        await self._sla.asignar_version_vigente(solicitud, contexto.actor_id)
        despues = {campo: getattr(solicitud, campo) for campo in _CAMPOS_AUDITADOS}
        await self._auditoria.registrar(
            contexto,
            action=ACCION_CORREGIDA,
            entity_type=ENTIDAD_SOLICITUD,
            entity_id=solicitud.id,
            old_values=antes,
            new_values={**despues, "result_id": resultado.id, "justification": datos.justification},
        )
        await self._session.commit()
        return RevisionResult(
            request_id=solicitud.id, status=solicitud.status, priority=solicitud.priority
        )
