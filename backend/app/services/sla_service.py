"""Casos de uso de los acuerdos de nivel de servicio versionados (HU-08.1).

Criterios de aceptación cubiertos:
- AC1: cada cambio registra una versión nueva con su fecha de entrada en vigor y
  conserva el histórico. Las versiones anteriores solo se cierran (`valid_to`); no
  se modifican, y `resolve_effective` devuelve el acuerdo vigente en la fecha en
  que se registró una solicitud.
- AC2: se rechaza una resolución menor o igual a la primera respuesta.
- AC3: si una combinación categoría-prioridad no tiene acuerdo, se aplica el
  predeterminado y se devuelve un aviso para notificar la omisión.

`asignar_version_vigente` liga una solicitud con la versión vigente al fijar su
prioridad (S4-13 y S4-16); de esa versión salen la fecha compromiso y el monitor del
umbral de riesgo (S4-08).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.logging import get_logger, log_event
from app.domain.auditoria import AuditContext, snapshot
from app.domain.sla_options import (
    AGREEMENT_DEFAULT_NAME,
    SERVICE_TYPE_NAMES,
    is_allowed_agreement_name,
)
from app.models.enums import Priority
from app.models.request import Request, RequestLog
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.repositories.sla_repository import SlaRepository
from app.schemas.sla import SlaAgreementCreate, SlaVersionCreate
from app.services.auditoria_service import AuditoriaService

logger = get_logger("sla")

ACCION_SIN_ACUERDO = "Sin acuerdo de nivel de servicio vigente"

CAMPOS_ACUERDO = ("id", "name", "category_id", "is_default", "is_active")
CAMPOS_VERSION = (
    "id",
    "agreement_id",
    "version",
    "priority",
    "first_response_minutes",
    "resolution_minutes",
    "valid_from",
    "valid_to",
)


class SlaNotFoundError(NotFoundError):
    """El acuerdo solicitado no existe."""


class SlaConflictError(ConflictError):
    """La operación choca con un acuerdo que ya existe."""


class SlaValidationError(BusinessRuleError):
    """Los datos no cumplen las reglas del acuerdo de nivel de servicio."""


class SlaNameNotAllowedError(SlaValidationError):
    """El nombre del acuerdo no está en la lista de tipos de servicio."""

    code = "sla_name_not_allowed"


class SlaNotConfiguredError(NotFoundError):
    """No hay acuerdo propio ni predeterminado para la combinación solicitada."""


@dataclass(frozen=True)
class EffectiveSla:
    agreement_id: uuid.UUID
    agreement_name: str
    version_id: uuid.UUID
    version: int
    priority: Priority
    first_response_minutes: int
    resolution_minutes: int
    valid_from: datetime
    used_default: bool
    notice: str | None


def as_utc(value: datetime) -> datetime:
    """Normaliza a UTC; un valor sin zona horaria se interpreta como UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SlaService:
    def __init__(self, repository: SlaRepository, auditoria: AuditoriaService) -> None:
        self._repository = repository
        self._auditoria = auditoria

    # --- acuerdos ----------------------------------------------------------
    @staticmethod
    def list_options() -> tuple[str, list[str]]:
        """Nombre fijo del predeterminado y tipos de servicio para acuerdos por categoría."""
        return AGREEMENT_DEFAULT_NAME, list(SERVICE_TYPE_NAMES)

    async def list_agreements(self) -> list[ServiceLevelAgreement]:
        return await self._repository.list_agreements()

    async def create_agreement(
        self, payload: SlaAgreementCreate, contexto: AuditContext | None = None
    ) -> ServiceLevelAgreement:
        if payload.is_default:
            # El predeterminado siempre lleva el nombre fijo; se ignora el enviado.
            name = AGREEMENT_DEFAULT_NAME
            if await self._repository.find_default() is not None:
                raise SlaConflictError("Ya existe un acuerdo predeterminado activo.")
        else:
            assert payload.category_id is not None
            name = (payload.name or "").strip()
            if not is_allowed_agreement_name(name):
                raise SlaNameNotAllowedError(
                    "El nombre del acuerdo debe ser uno de los tipos de servicio disponibles."
                )
            if not await self._repository.category_exists(payload.category_id):
                raise SlaValidationError(f"La categoría {payload.category_id} no existe.")
            if any(
                existing.is_active
                and existing.name == name
                and existing.category_id == payload.category_id
                for existing in await self._repository.list_agreements()
            ):
                raise SlaConflictError(f"Ya existe un acuerdo activo «{name}» para esta categoría.")
            if await self._repository.find_active_for_category(payload.category_id) is not None:
                raise SlaConflictError("La categoría ya tiene un acuerdo activo.")

        agreement = ServiceLevelAgreement(
            name=name,
            category_id=payload.category_id,
            is_default=payload.is_default,
            is_active=True,
        )
        created = await self._repository.add_agreement(agreement)
        await self._auditoria.registrar(
            contexto,
            action="sla.acuerdo.creado",
            entity_type="sla_agreement",
            entity_id=created.id,
            new_values=snapshot(created, CAMPOS_ACUERDO),
        )
        await self._repository.commit()
        return created

    # --- versiones (AC1, AC2) ----------------------------------------------
    async def publish_version(
        self,
        agreement_id: uuid.UUID,
        payload: SlaVersionCreate,
        contexto: AuditContext | None = None,
    ) -> list[ServiceLevelVersion]:
        agreement = await self._repository.get_agreement(agreement_id)
        if agreement is None:
            raise SlaNotFoundError(f"No existe el acuerdo {agreement_id}.")
        if not agreement.is_active:
            raise SlaValidationError("El acuerdo está inactivo y no admite versiones nuevas.")

        valid_from = as_utc(payload.valid_from)
        closing: list[ServiceLevelVersion] = []
        for times in payload.times:
            if times.resolution_minutes <= times.first_response_minutes:
                raise SlaValidationError(
                    f"Inconsistencia en {times.priority.value}: el tiempo de resolución debe "
                    "ser mayor que el de primera respuesta."
                )
            current = await self._repository.open_version(agreement_id, times.priority.value)
            if current is not None:
                if as_utc(current.valid_from) >= valid_from:
                    raise SlaValidationError(
                        f"La fecha de entrada en vigor debe ser posterior a la de la versión "
                        f"{current.version} de {times.priority.value}."
                    )
                closing.append(current)

        next_number = await self._repository.latest_version_number(agreement_id) + 1
        for current in closing:
            current.valid_to = valid_from
        new_versions = [
            ServiceLevelVersion(
                agreement_id=agreement_id,
                version=next_number,
                priority=times.priority.value,
                first_response_minutes=times.first_response_minutes,
                resolution_minutes=times.resolution_minutes,
                valid_from=valid_from,
            )
            for times in payload.times
        ]
        saved = await self._repository.save_versions(new_versions)
        for version in saved:
            await self._auditoria.registrar(
                contexto,
                action="sla.version.creada",
                entity_type="sla_version",
                entity_id=version.id,
                new_values=snapshot(version, CAMPOS_VERSION),
            )
        await self._repository.commit()
        return saved

    async def list_versions(
        self, agreement_id: uuid.UUID, *, priority: Priority | None = None
    ) -> list[ServiceLevelVersion]:
        if await self._repository.get_agreement(agreement_id) is None:
            raise SlaNotFoundError(f"No existe el acuerdo {agreement_id}.")
        return await self._repository.list_versions(
            agreement_id, priority=priority.value if priority else None
        )

    # --- acuerdo vigente y predeterminado (AC1, AC3) ------------------------
    async def resolve_effective(
        self,
        category_id: uuid.UUID | None,
        priority: Priority,
        at: datetime | None = None,
    ) -> EffectiveSla:
        moment = as_utc(at) if at is not None else datetime.now(UTC)

        if category_id is not None:
            own = await self._repository.find_active_for_category(category_id)
            if own is not None:
                version = await self._repository.find_effective(own.id, priority.value, moment)
                if version is not None:
                    return self._build(own, version, used_default=False, notice=None)

        default = await self._repository.find_default()
        if default is not None:
            version = await self._repository.find_effective(default.id, priority.value, moment)
            if version is not None:
                notice = (
                    f"No hay acuerdo configurado para la categoría y la prioridad "
                    f"{priority.value}; se aplicó el acuerdo predeterminado «{default.name}»."
                )
                return self._build(default, version, used_default=True, notice=notice)

        raise SlaNotConfiguredError(
            f"No hay acuerdo propio ni predeterminado para la prioridad {priority.value}."
        )

    async def asignar_version_vigente(
        self, request: Request, author_id: uuid.UUID
    ) -> EffectiveSla | None:
        """Asigna a la solicitud la versión del acuerdo vigente en su fecha de registro.

        Usa el acuerdo de su categoría o, si no tiene, el predeterminado, para la prioridad
        ya calculada. Si no hay versión vigente, la solicitud sigue sin acuerdo: se registra
        el evento, se deja constancia en la bitácora y se devuelve `None` sin fallar. No
        confirma; la transacción la cierra el servicio que orquesta.
        """
        if request.priority is None:
            return None
        prioridad = Priority(request.priority)
        try:
            vigente = await self.resolve_effective(
                request.category_id, prioridad, request.created_at
            )
        except SlaNotConfiguredError as exc:
            log_event(
                logger,
                "sla_sin_version_vigente",
                level="WARNING",
                folio=request.folio,
                prioridad=prioridad.value,
            )
            await self._repository.add_log(
                RequestLog(
                    request_id=request.id,
                    author_id=author_id,
                    action=ACCION_SIN_ACUERDO,
                    notes=f"{exc} La solicitud continúa sin fecha compromiso.",
                )
            )
            return None
        request.service_level_version = await self._repository.get_version(vigente.version_id)
        request.service_level_version_id = vigente.version_id
        if vigente.notice is not None:
            log_event(logger, "sla_predeterminado_aplicado", folio=request.folio)
        return vigente

    @staticmethod
    def _build(
        agreement: ServiceLevelAgreement,
        version: ServiceLevelVersion,
        *,
        used_default: bool,
        notice: str | None,
    ) -> EffectiveSla:
        return EffectiveSla(
            agreement_id=agreement.id,
            agreement_name=agreement.name,
            version_id=version.id,
            version=version.version,
            priority=Priority(version.priority),
            first_response_minutes=version.first_response_minutes,
            resolution_minutes=version.resolution_minutes,
            valid_from=as_utc(version.valid_from),
            used_default=used_default,
            notice=notice,
        )
