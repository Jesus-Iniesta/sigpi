"""Cálculo centralizado de la prioridad de una solicitud (HU-02.3, RN-05).

La prioridad nunca se captura: se deriva siempre de la urgencia y el impacto con
la matriz del dominio. Todo código que necesite la prioridad pasa por este
servicio, de modo que existe un único punto donde se aplica la regla.
"""

from app.domain.priority import calculate_priority
from app.models.enums import Priority
from app.models.request import Request


class PrioridadInvalidaError(ValueError):
    """La urgencia o el impacto están fuera de la matriz (deben ser enteros de 1 a 3)."""


class PrioridadService:
    def calcular(self, urgency: int | None, impact: int | None) -> Priority | None:
        """Devuelve la prioridad, o `None` si aún falta la urgencia o el impacto."""
        if urgency is None or impact is None:
            return None
        try:
            return calculate_priority(urgency, impact)
        except ValueError as exc:
            raise PrioridadInvalidaError(str(exc)) from exc

    def aplicar(self, request: Request) -> Priority | None:
        """Calcula la prioridad con los valores de la solicitud y la asigna."""
        request.priority = self.calcular(request.urgency, request.impact)
        return request.priority
