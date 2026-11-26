"""Esquemas de respuesta de los indicadores del servicio (S5-05)."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class ConteoDiaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fecha: date
    total: int


class ResumenIndicadoresRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    desde: date
    hasta: date
    total: int
    por_estatus: dict[str, int]
    por_prioridad: dict[str, int]
    por_categoria: dict[str, int]
    resueltas_con_sla: int
    resueltas_en_tiempo: int
    cumplimiento_sla: float
    tiempo_medio_primera_respuesta_min: float
    tiempo_medio_resolucion_min: float
    abiertas_vencidas: int
    por_dia: list[ConteoDiaRead]
