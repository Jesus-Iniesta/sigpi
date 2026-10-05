"""Casos de uso de los acuerdos de nivel de servicio versionados (HU-08.1).

Criterios de aceptación cubiertos:
- AC1: cada cambio registra una versión nueva con su fecha de entrada en vigor y
  conserva el histórico. Las versiones anteriores solo se cierran (`valid_to`); no
  se modifican, y `resolve_effective` devuelve el acuerdo vigente en la fecha en
  que se registró una solicitud.
- AC2: se rechaza una resolución menor o igual a la primera respuesta.
- AC3: si una combinación categoría-prioridad no tiene acuerdo, se aplica el
  predeterminado y se devuelve un aviso para notificar la omisión.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.models.enums import Priority
from app.models.sla import ServiceLevelAgreement, ServiceLevelVersion
from app.repositories.sla_repository import SlaRepository
from app.schemas.sla import SlaAgreementCreate, SlaVersionCreate


class SlaNotFoundError(LookupError):
    """El acuerdo solicitado no existe."""


class SlaConflictError(ValueError):
    """La operación choca con un acuerdo que ya existe."""


class SlaValidationError(ValueError):
    """Los datos no cumplen las reglas del acuerdo de nivel de servicio."""


class SlaNotConfiguredError(LookupError):
    """No hay acuerdo propio ni predeterminado para la combinación solicitada."""


@dataclass(frozen=True)
class EffectiveSla:
    agreement_id: uuid.UUID
    agreement_name: str
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
    def __init__(self, repository: SlaRepository) -> None:
        self._repository = repository

    # --- acuerdos ----------------------------------------------------------
    async def list_agreements(self) -> list[ServiceLevelAgreement]:
        return await self._repository.list_agreements()

    async def create_agreement(self, payload: SlaAgreementCreate) -> ServiceLevelAgreement:
        if payload.is_default:
            if await self._repository.find_default() is not None:
                raise SlaConflictError("Ya existe un acuerdo predeterminado activo.")
        else:
            assert payload.category_id is not None
            if not await self._repository.category_exists(payload.category_id):
                raise SlaValidationError(f"La categoría {payload.category_id} no existe.")
            if await self._repository.find_active_for_category(payload.category_id) is not None:
                raise SlaConflictError("La categoría ya tiene un acuerdo activo.")

        agreement = ServiceLevelAgreement(
            name=payload.name,
            category_id=payload.category_id,
            is_default=payload.is_default,
            is_active=True,
        )
        return await self._repository.add_agreement(agreement)

    # --- versiones (AC1, AC2) ----------------------------------------------
    async def publish_version(
        self, agreement_id: uuid.UUID, payload: SlaVersionCreate
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
        return await self._repository.save_versions(new_versions)

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
            version=version.version,
            priority=Priority(version.priority),
            first_response_minutes=version.first_response_minutes,
            resolution_minutes=version.resolution_minutes,
            valid_from=as_utc(version.valid_from),
            used_default=used_default,
            notice=notice,
        )
