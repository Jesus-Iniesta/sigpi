"""Reglas puras de la clasificación automática (S4-14, HU-02.2).

No depende de FastAPI ni de SQLAlchemy: recibe números y devuelve decisiones.
"""


def requiere_revision(confianza: float, umbral: float) -> bool:
    """RN-06: una clasificación con confianza estrictamente menor que el umbral la revisa
    una persona. Con la confianza exactamente igual al umbral se acepta tal cual."""
    return float(confianza) < float(umbral)
