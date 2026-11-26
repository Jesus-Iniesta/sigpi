"""Esquemas de la asignación de técnicos (S5-03, HU-03.1)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from app.domain.asignacion import Propuesta, desglose_desde_texto
from app.models.enums import RequestStatus

if TYPE_CHECKING:
    from app.models.request import RequestAssignment
    from app.services.asignacion_service import Asignado


class ComponentePuntaje(BaseModel):
    concepto: str
    puntos: int
    detalle: str


class CandidatoRead(BaseModel):
    """Técnico candidato con su puntaje y el desglose que lo explica."""

    technician_id: uuid.UUID
    full_name: str
    score: int
    active_load: int
    score_breakdown: str
    components: list[ComponentePuntaje]

    @classmethod
    def from_propuesta(cls, propuesta: Propuesta) -> "CandidatoRead":
        return cls(
            technician_id=propuesta.technician_id,
            full_name=propuesta.nombre,
            score=propuesta.score,
            active_load=propuesta.carga,
            score_breakdown=propuesta.score_breakdown,
            components=[
                ComponentePuntaje(concepto=c.concepto, puntos=c.puntos, detalle=c.detalle)
                for c in propuesta.desglose
            ],
        )


class AsignacionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technician_id: uuid.UUID


class AsignacionRead(BaseModel):
    """Asignación vigente tras asignar, con el estatus en que quedó la solicitud."""

    id: uuid.UUID
    request_id: uuid.UUID
    technician_id: uuid.UUID
    score: float | None
    score_breakdown: str | None
    is_automatic: bool
    assigned_at: datetime
    unassigned_at: datetime | None
    request_status: RequestStatus

    @classmethod
    def from_model(cls, asignado: "Asignado") -> "AsignacionRead":
        asignacion = asignado.asignacion
        return cls(
            id=asignacion.id,
            request_id=asignacion.request_id,
            technician_id=asignacion.technician_id,
            score=asignacion.score,
            score_breakdown=asignacion.score_breakdown,
            is_automatic=asignacion.is_automatic,
            assigned_at=asignacion.assigned_at,
            unassigned_at=asignacion.unassigned_at,
            request_status=asignado.estado,
        )


class AsignacionVigenteRead(BaseModel):
    """Técnico asignado a la solicitud y el puntaje con el que se eligió (S5-12).

    `components` sale de `score_breakdown`; queda vacío si la asignación no tiene puntaje
    (por ejemplo, la que ya existía antes del motor de asignación).
    """

    id: uuid.UUID
    request_id: uuid.UUID
    technician_id: uuid.UUID
    full_name: str
    score: float | None
    score_breakdown: str | None
    components: list[ComponentePuntaje]
    is_automatic: bool
    assigned_at: datetime

    @classmethod
    def from_model(cls, asignacion: "RequestAssignment") -> "AsignacionVigenteRead":
        return cls(
            id=asignacion.id,
            request_id=asignacion.request_id,
            technician_id=asignacion.technician_id,
            full_name=asignacion.technician.full_name,
            score=asignacion.score,
            score_breakdown=asignacion.score_breakdown,
            components=[
                ComponentePuntaje(concepto=c.concepto, puntos=c.puntos, detalle=c.detalle)
                for c in desglose_desde_texto(asignacion.score_breakdown)
            ],
            is_automatic=asignacion.is_automatic,
            assigned_at=asignacion.assigned_at,
        )
