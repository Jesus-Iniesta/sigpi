"""Nombres permitidos para los acuerdos de servicio (COR-05, HU-08.1).

El acuerdo predeterminado lleva siempre el mismo nombre; los acuerdos por categoría
eligen su nombre de esta lista de tipos de servicio. El equipo puede ajustar los textos.
"""

AGREEMENT_DEFAULT_NAME = "Acuerdo general de servicio"

SERVICE_TYPE_NAMES: tuple[str, ...] = (
    "Soporte a equipo de cómputo y periféricos",
    "Soporte de software y aplicaciones",
    "Conectividad y redes",
    "Cuentas y accesos institucionales",
)


def is_allowed_agreement_name(name: str) -> bool:
    """Indica si `name` es uno de los tipos de servicio permitidos."""
    return name in SERVICE_TYPE_NAMES


# Descripción fija del servicio que se imprime en el contrato simulado (COR-06A).
SERVICE_DESCRIPTIONS: dict[str, str] = {
    AGREEMENT_DEFAULT_NAME: (
        "Atención general de solicitudes de soporte técnico de la comunidad universitaria "
        "de la Facultad de Ingeniería que no cuentan con un acuerdo específico por categoría."
    ),
    "Soporte a equipo de cómputo y periféricos": (
        "Diagnóstico, mantenimiento correctivo y puesta en marcha de equipos de cómputo, "
        "impresoras, proyectores y demás periféricos asignados a la Facultad."
    ),
    "Soporte de software y aplicaciones": (
        "Instalación, configuración y solución de fallas de sistemas operativos, paquetería "
        "institucional y aplicaciones de uso académico o administrativo."
    ),
    "Conectividad y redes": (
        "Atención de fallas de conexión a la red cableada e inalámbrica, configuración de "
        "puntos de red y orientación sobre el acceso a los servicios de red de la Facultad."
    ),
    "Cuentas y accesos institucionales": (
        "Alta, restablecimiento y desbloqueo de cuentas institucionales, así como la gestión "
        "de accesos a los sistemas y plataformas de la Universidad."
    ),
}

SERVICE_DESCRIPTION_FALLBACK = (
    "Atención de solicitudes de soporte técnico conforme al catálogo de servicios del DTIC-FI."
)


def service_description(name: str) -> str:
    """Texto fijo que describe el tipo de servicio en el contrato simulado."""
    return SERVICE_DESCRIPTIONS.get(name, SERVICE_DESCRIPTION_FALLBACK)
