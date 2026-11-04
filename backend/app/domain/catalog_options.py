"""Opciones predefinidas del catálogo de técnicos (HU-11.1, COR-04).

Fuente única de verdad de los nombres que se pueden registrar en el catálogo.
Los esquemas, el servicio, las semillas y el endpoint `GET /catalog/options`
leen de aquí, así que el frontend no duplica las listas.

Este módulo es dominio puro: no importa FastAPI ni SQLAlchemy.
"""

import unicodedata
from dataclasses import dataclass

SERVICE_AREA_OPTIONS: tuple[str, ...] = (
    "Soporte a usuarios",
    "Infraestructura y redes",
    "Sistemas y aplicaciones",
    "Laboratorios y aulas",
)

CATEGORY_OPTIONS: tuple[str, ...] = (
    "Hardware",
    "Software",
    "Redes",
    "Cuentas y accesos",
)

# Especialidades agrupadas por el nombre de la categoría a la que pertenecen.
SPECIALTY_OPTIONS: dict[str, tuple[str, ...]] = {
    "Hardware": (
        "Equipo de cómputo",
        "Impresoras y periféricos",
        "Proyectores y audiovisual",
    ),
    "Software": (
        "Sistemas operativos",
        "Paquetería de oficina",
        "Software académico especializado",
        "Antivirus y seguridad",
    ),
    "Redes": (
        "Red cableada",
        "Red inalámbrica (Wi-Fi)",
        "VPN y acceso remoto",
    ),
    "Cuentas y accesos": (
        "Correo institucional",
        "Restablecimiento de contraseñas",
        "Permisos en plataformas institucionales",
    ),
}


@dataclass(frozen=True)
class ShiftOption:
    """Turno con su horario fijo, en minutos desde la medianoche."""

    name: str
    start_minute: int
    end_minute: int


SHIFT_OPTIONS: tuple[ShiftOption, ...] = (
    ShiftOption("Matutino", 7 * 60, 15 * 60),
    ShiftOption("Vespertino", 13 * 60, 21 * 60),
    ShiftOption("Mixto", 9 * 60, 17 * 60),
)

MAX_LOAD_MIN = 1
MAX_LOAD_MAX = 15

DESCRIPTION_MAX_LENGTH = 300


class CatalogOptionError(ValueError):
    """El valor no pertenece a la lista de opciones permitidas."""

    def __init__(self, label: str, value: str, allowed: tuple[str, ...]) -> None:
        self.value = value
        self.allowed = allowed
        listado = ", ".join(allowed) if allowed else "ninguno"
        super().__init__(
            f"«{value}» no es una opción permitida para {label}. Valores permitidos: {listado}."
        )


def ensure_option(label: str, value: str, allowed: tuple[str, ...]) -> str:
    """Devuelve `value` si está en `allowed`; si no, lanza `CatalogOptionError`."""
    if value not in allowed:
        raise CatalogOptionError(label, value, allowed)
    return value


def specialties_for(category_name: str) -> tuple[str, ...]:
    """Especialidades permitidas para una categoría (vacío si la categoría no es estándar)."""
    return SPECIALTY_OPTIONS.get(category_name, ())


def shift_option(name: str) -> ShiftOption:
    """Turno predefinido con ese nombre; lanza `CatalogOptionError` si no existe."""
    for option in SHIFT_OPTIONS:
        if option.name == name:
            return option
    raise CatalogOptionError("el turno", name, tuple(o.name for o in SHIFT_OPTIONS))


def validate_description(value: str) -> str:
    """Valida una descripción ya recortada: sin caracteres de control ni etiquetas HTML."""
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError("La descripción no puede contener caracteres de control.")
    if "<" in value or ">" in value:
        raise ValueError("La descripción no puede contener etiquetas HTML (< o >).")
    if len(value) > DESCRIPTION_MAX_LENGTH:
        raise ValueError(f"La descripción no puede superar {DESCRIPTION_MAX_LENGTH} caracteres.")
    return value
