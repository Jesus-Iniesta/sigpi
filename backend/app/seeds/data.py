from app.models.enums import Priority

CATEGORY_SEEDS: tuple[tuple[str, str], ...] = (
    ("Hardware", "Incidencias relacionadas con equipos y periféricos."),
    ("Software", "Incidencias relacionadas con aplicaciones y sistemas."),
    ("Redes", "Incidencias relacionadas con conectividad y comunicaciones."),
    ("Cuentas y accesos", "Incidencias relacionadas con autenticación y permisos."),
)

PRIORITY_SEEDS: tuple[Priority, ...] = tuple(Priority)