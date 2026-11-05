"""Reglas puras de la bitácora de auditoría (S2-08, HU-10.3).

Convierte entidades en instantáneas JSON seguras para guardarlas en `audit_logs`
y calcula qué campos cambiaron en una modificación. Este módulo es dominio puro:
no importa FastAPI ni SQLAlchemy.
"""

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

# Campos que nunca deben llegar a la bitácora, aunque se pidan explícitamente.
CAMPOS_SENSIBLES: frozenset[str] = frozenset(
    {"password", "password_hash", "token", "access_token", "refresh_token"}
)
_FRAGMENTOS_SENSIBLES: tuple[str, ...] = ("password", "token")


@dataclass(frozen=True)
class AuditContext:
    """Quién hace el cambio y desde dónde; lo arma la capa HTTP en cada petición."""

    actor_id: uuid.UUID | None = None
    ip_address: str | None = None


def es_campo_sensible(campo: str) -> bool:
    """Indica si el campo contiene credenciales o tokens y debe excluirse."""
    nombre = campo.lower()
    return nombre in CAMPOS_SENSIBLES or any(f in nombre for f in _FRAGMENTOS_SENSIBLES)


def a_json(valor: Any) -> Any:
    """Convierte un valor a un tipo serializable en JSON (UUID y fechas a texto)."""
    if valor is None or isinstance(valor, bool | int | float | str):
        return valor
    if isinstance(valor, Enum):
        return a_json(valor.value)
    if isinstance(valor, uuid.UUID | Decimal):
        return str(valor)
    if isinstance(valor, datetime | date | time):
        return valor.isoformat()
    if isinstance(valor, Mapping):
        return {str(k): a_json(v) for k, v in valor.items() if not es_campo_sensible(str(k))}
    if isinstance(valor, list | tuple | set | frozenset):
        return [a_json(v) for v in valor]
    return str(valor)


def snapshot(obj: Any, campos: Iterable[str]) -> dict[str, Any]:
    """Instantánea JSON de los `campos` de `obj`, sin datos sensibles.

    `obj` puede ser cualquier objeto con atributos o un `Mapping`. Los campos de la
    lista negra (`password`, `password_hash`, tokens) se descartan siempre.
    """
    resultado: dict[str, Any] = {}
    for campo in campos:
        if es_campo_sensible(campo):
            continue
        valor = obj.get(campo) if isinstance(obj, Mapping) else getattr(obj, campo)
        resultado[campo] = a_json(valor)
    return resultado


def campos_modificados(
    antes: Mapping[str, Any], despues: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Devuelve `(old_values, new_values)` solo con los campos que cambiaron."""
    claves = [k for k in despues if antes.get(k) != despues.get(k)]
    claves += [k for k in antes if k not in despues]
    return {k: antes.get(k) for k in claves}, {k: despues.get(k) for k in claves}
