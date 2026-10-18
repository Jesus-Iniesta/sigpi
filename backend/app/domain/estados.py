"""Reglas de estados de la solicitud: «En espera» (HU-04.2) y «Por verificar» (HU-01.3).

El reloj del SLA solo se suspende mientras la solicitud espera algo ajeno al
equipo de soporte (un insumo externo o información del solicitante). Estas
reglas son puras: no consultan la base de datos.
"""

from app.models.enums import RequestStatus

# Estados desde los que una solicitud puede pasar a «En espera».
ESTADOS_QUE_PUEDEN_ESPERAR: frozenset[RequestStatus] = frozenset(
    {RequestStatus.ASSIGNED, RequestStatus.IN_PROGRESS}
)

# Estado al que regresa una solicitud cuando se reanuda el reloj.
ESTADO_AL_REANUDAR = RequestStatus.IN_PROGRESS


def puede_suspender(status: RequestStatus) -> bool:
    return status in ESTADOS_QUE_PUEDEN_ESPERAR


def puede_reanudar(status: RequestStatus) -> bool:
    return status == RequestStatus.WAITING


def estado_inicial(solicitante_localizado: bool) -> RequestStatus:
    """Estado con el que se registra una solicitud nueva.

    Un solicitante no localizado no impide el registro: la solicitud queda
    pendiente de verificación hasta que se confirme quién es.
    """
    if solicitante_localizado:
        return RequestStatus.REGISTERED
    return RequestStatus.PENDING_VERIFICATION
