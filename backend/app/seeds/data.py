from app.core.permissions import RoleName
from app.models.enums import Priority, SupportLevel, UserType

CATEGORY_SEEDS: tuple[tuple[str, str], ...] = (
    ("Hardware", "Incidencias relacionadas con equipos y periféricos."),
    ("Software", "Incidencias relacionadas con aplicaciones y sistemas."),
    ("Redes", "Incidencias relacionadas con conectividad y comunicaciones."),
    ("Cuentas y accesos", "Incidencias relacionadas con autenticación y permisos."),
)

PRIORITY_SEEDS: tuple[Priority, ...] = tuple(Priority)

USER_SEEDS: tuple[dict, ...] = (
    {
        "institutional_id": "uaem2026001",
        "password": "ClaveSegura#2026",
        "full_name": "Ana Martínez Soto",
        "email": "amartinez@uaemex.mx",
        "user_type": UserType.ADMINISTRATIVE,
        "role": RoleName.ADMINISTRATOR,
        "support_level": None,
        "max_load": None,
    },
    {
        "institutional_id": "uaem2026002",
        "password": "ClaveSegura#2026",
        "full_name": "Carlos Rodríguez López",
        "email": "crodriguez@uaemex.mx",
        "user_type": UserType.TECHNICAL,
        "role": RoleName.SUPPORT_AGENT,
        "support_level": SupportLevel.LEVEL_1,
        "max_load": 8,
    },
    {
        "institutional_id": "uaem2026003",
        "password": "ClaveSegura#2026",
        "full_name": "Elena García Ruiz",
        "email": "egarcia@uaemex.mx",
        "user_type": UserType.ACADEMIC,
        "role": RoleName.REQUESTER,
        "support_level": None,
        "max_load": None,
    },
    {
        "institutional_id": "uaem2026004",
        "password": "ClaveSegura#2026",
        "full_name": "Luis Hernández Méndez",
        "email": "lhernandez@uaemex.mx",
        "user_type": UserType.TECHNICAL,
        "role": RoleName.SUPPORT_AGENT,
        "support_level": SupportLevel.LEVEL_2,
        "max_load": 10,
    },
)
