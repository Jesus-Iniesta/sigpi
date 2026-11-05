"""Pruebas del helper de instantáneas de auditoría (S2-08, HU-10.3)."""

import json
import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.domain.auditoria import campos_modificados, snapshot
from app.models.enums import SupportLevel


def test_snapshot_serializa_uuid_fechas_y_enums_a_json() -> None:
    obj_id = uuid.uuid4()
    obj = SimpleNamespace(
        id=obj_id,
        valid_from=datetime(2026, 1, 1, 8, 30, tzinfo=UTC),
        dia=date(2026, 1, 2),
        support_level=SupportLevel.LEVEL_2,
        max_load=5,
    )

    datos = snapshot(obj, ["id", "valid_from", "dia", "support_level", "max_load"])

    assert datos == {
        "id": str(obj_id),
        "valid_from": "2026-01-01T08:30:00+00:00",
        "dia": "2026-01-02",
        "support_level": "level_2",
        "max_load": 5,
    }
    json.dumps(datos)  # no lanza: todo es serializable


def test_snapshot_excluye_password_hash_y_tokens_aunque_se_pidan() -> None:
    obj = SimpleNamespace(
        email="a@uaemex.mx",
        password="secreta",
        password_hash="$2b$12$hash",
        access_token="jwt",
        refresh_token="otro",
    )

    datos = snapshot(obj, ["email", "password", "password_hash", "access_token", "refresh_token"])

    assert datos == {"email": "a@uaemex.mx"}


def test_snapshot_limpia_datos_sensibles_anidados_y_acepta_mappings() -> None:
    datos = snapshot({"perfil": {"password": "x", "nombre": "Ana"}}, ["perfil"])

    assert datos == {"perfil": {"nombre": "Ana"}}


def test_campos_modificados_devuelve_solo_lo_que_cambio() -> None:
    antes = {"max_load": 5, "shift_id": None, "support_level": "level_1"}
    despues = {"max_load": 8, "shift_id": None, "support_level": "level_1"}

    assert campos_modificados(antes, despues) == ({"max_load": 5}, {"max_load": 8})


def test_campos_modificados_sin_cambios_devuelve_diccionarios_vacios() -> None:
    assert campos_modificados({"a": 1}, {"a": 1}) == ({}, {})
