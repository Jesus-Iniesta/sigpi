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
