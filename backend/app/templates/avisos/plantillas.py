"""Textos de cada aviso, por código de evento (S4-04, HU-07.1).

La semilla `python -m app.seeds notifications` los carga en `notification_templates`;
si la tabla no tiene la plantilla, `notificacion_service` usa estos mismos textos.
"""

from app.domain.eventos import EventoAviso

# código de evento -> (asunto, cuerpo). Los campos entre llaves salen de `_contexto`.
PLANTILLAS_AVISO: dict[str, tuple[str, str]] = {
    EventoAviso.SOLICITUD_REGISTRADA: (
        "Solicitud {folio} registrada",
        (
            "Registramos tu solicitud «{titulo}».\n"
            "Folio: {folio} · Categoría: {categoria} · Prioridad: {prioridad}\n"
            "Técnico: {tecnico} · Fecha compromiso: {fecha_compromiso}"
        ),
    ),
    EventoAviso.SOLICITUD_ASIGNADA: (
        "Solicitud {folio} asignada",
        (
            "La solicitud «{titulo}» tiene técnico asignado.\n"
            "Folio: {folio} · Categoría: {categoria} · Prioridad: {prioridad}\n"
            "Técnico: {tecnico} · Fecha compromiso: {fecha_compromiso}"
        ),
    ),
    EventoAviso.ESTATUS_CAMBIADO: (
        "Solicitud {folio}: {estado}",
        (
            "La solicitud «{titulo}» cambió de estatus a {estado}.\n"
            "Folio: {folio} · Categoría: {categoria} · Prioridad: {prioridad}\n"
            "Técnico: {tecnico} · Fecha compromiso: {fecha_compromiso}"
        ),
    ),
    EventoAviso.SOLICITUD_RESUELTA: (
        "Solicitud {folio} resuelta",
        (
            "El técnico resolvió «{titulo}». Confirma si la solución funcionó.\n"
            "Folio: {folio} · Categoría: {categoria} · Prioridad: {prioridad}\n"
            "Técnico: {tecnico} · Fecha compromiso: {fecha_compromiso}"
        ),
    ),
    EventoAviso.SOLICITUD_CERRADA: (
        "Solicitud {folio} cerrada",
        (
            "Cerramos la solicitud «{titulo}».\n"
            "Folio: {folio} · Categoría: {categoria} · Prioridad: {prioridad}\n"
            "Técnico: {tecnico} · Fecha compromiso: {fecha_compromiso}"
        ),
    ),
    EventoAviso.RIESGO_SLA: (
        "Riesgo de incumplir {folio}",
        (
            "La solicitud «{titulo}» ya consumió el 80 % del tiempo comprometido.\n"
            "Folio: {folio} · Prioridad: {prioridad} · Técnico: {tecnico}\n"
            "Fecha compromiso: {fecha_compromiso}"
        ),
    ),
    EventoAviso.P1_SIN_ASIGNAR: (
        "Solicitud crítica {folio} sin asignar",
        (
            "La solicitud P1 «{titulo}» lleva cinco minutos sin técnico asignado.\n"
            "Folio: {folio} · Categoría: {categoria} · Fecha compromiso: {fecha_compromiso}"
        ),
    ),
}
