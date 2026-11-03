"""Pruebas del formato del correo institucional (COR-01, HU-01.1)."""

import pytest
from pydantic import ValidationError

from app.core.security import INSTITUTIONAL_EMAIL_DOMAINS, is_institutional_email
from app.schemas.auth import LoginRequest

MENSAJE = "El correo debe ser institucional (@uaemex.mx o @alumno.uaemex.mx)."


def test_los_dominios_aceptados_son_exactamente_dos() -> None:
    assert INSTITUTIONAL_EMAIL_DOMAINS == ("uaemex.mx", "alumno.uaemex.mx")


@pytest.mark.parametrize(
    "email",
    [
        "amartinez@uaemex.mx",
        "ldiazm@alumno.uaemex.mx",
        "AMartinez@UAEMEX.MX",
        "LDiazM@Alumno.UAEMex.mx",
    ],
)
def test_acepta_los_dominios_institucionales(email: str) -> None:
    assert is_institutional_email(email)


@pytest.mark.parametrize(
    "email",
    [
        "alguien@gmail.com",
        "alguien@uaemex.mx.evil.com",
        "alguien@otro.uaemex.mx",
        "alguien@x.uaemex.mx",
        "alguien@alumno.uaemex.mx.evil.com",
        "alguien@evilalumno.uaemex.mx",
        "alguien@fakeuaemex.mx",
        "@uaemex.mx",
        "uaemex.mx",
        "alguien@uaemex.mx\n",
    ],
)
def test_rechaza_dominios_no_listados(email: str) -> None:
    assert not is_institutional_email(email)


@pytest.mark.parametrize("email", ["ldiazm@alumno.uaemex.mx", " AMartinez@UAEMEX.MX "])
def test_login_request_acepta_y_normaliza_correos_institucionales(email: str) -> None:
    request = LoginRequest(email=email, password="x")

    assert request.email == email.strip().lower()


@pytest.mark.parametrize(
    "email", ["alguien@gmail.com", "alguien@uaemex.mx.evil.com", "alguien@otro.uaemex.mx"]
)
def test_login_request_rechaza_con_el_mensaje_nuevo(email: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        LoginRequest(email=email, password="x")

    assert MENSAJE in str(exc_info.value)
