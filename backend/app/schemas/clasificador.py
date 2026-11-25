"""Esquemas de la administración del clasificador (S5-06, HU-02.2, HU-12.1, HU-12.2)."""

from datetime import datetime

from pydantic import BaseModel, Field

UMBRAL_MINIMO = 0.50
UMBRAL_MAXIMO = 0.95


class UmbralInput(BaseModel):
    umbral: float = Field(ge=UMBRAL_MINIMO, le=UMBRAL_MAXIMO)


class UmbralResult(BaseModel):
    umbral_anterior: float
    umbral: float


class EstadoClasificador(BaseModel):
    version: str
    umbral: float
    ejemplos: int
    # Exactitud de categoría con validación cruzada; `None` si no se midió.
    exactitud: float | None
    correcciones_pendientes: int
    # Proporción de solicitudes recientes que la clasificación mandó a «Por revisar».
    proporcion_por_revisar: float | None
    dias_recientes: int
    entrenado_en: datetime | None


class ReentrenamientoResult(BaseModel):
    version: str
    exactitud: float
    ejemplos: int
    correcciones_incorporadas: int
    version_anterior: str
    exactitud_anterior: float | None
    activado: bool
    mensaje: str
