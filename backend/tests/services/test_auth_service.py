"""Pruebas unitarias de `AuthService.login` con un repositorio simulado (S5-24, HU-01.1).

Cubren los cuatro caminos: credenciales malas, contador de intentos fallidos
(con la oferta de recuperar la contraseña), cuenta inactiva y reinicio del
contador tras un inicio de sesión correcto.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.core.security import decode_access_token, hash_password
from app.services.auth_service import AuthService, InactiveAccountError, InvalidCredentialsError

CONTRASENA = "Contrasena-Segura-1"


class RepositorioSimulado:
    """Imita `AuthRepository` guardando los usuarios en memoria."""

    def __init__(self, *usuarios: SimpleNamespace) -> None:
        self.por_correo = {u.email: u for u in usuarios}
        self.por_id = {u.id: u for u in usuarios}
        self.intentos_guardados: list[int] = []

    async def get_by_email(self, email: str):
        return self.por_correo.get(email)

    async def get_by_id(self, user_id: uuid.UUID):
        return self.por_id.get(user_id)

    async def set_failed_attempts(self, user, attempts: int) -> None:
        user.failed_login_attempts = attempts
        self.intentos_guardados.append(attempts)


def _usuario(
    *,
    password_hash: str | None = None,
    is_active: bool = True,
    failed_login_attempts: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="tecnico@example.test",
        password_hash=hash_password(CONTRASENA) if password_hash is None else password_hash,
        is_active=is_active,
        failed_login_attempts=failed_login_attempts,
        # Un rol huérfano (role=None) no debe colarse en el token.
        roles=[
            SimpleNamespace(role=SimpleNamespace(name="support_agent")),
            SimpleNamespace(role=None),
        ],
    )


def _login(repositorio: RepositorioSimulado, email: str, password: str):
    return asyncio.run(AuthService(repositorio).login(email, password))


# --- Credenciales malas --------------------------------------------------------------


def test_un_correo_desconocido_no_cuenta_intentos() -> None:
    repositorio = RepositorioSimulado(_usuario())

    with pytest.raises(InvalidCredentialsError) as error:
        _login(repositorio, "nadie@example.test", CONTRASENA)

    assert error.value.failed_attempts == 0
    assert error.value.offer_password_recovery is False
    assert repositorio.intentos_guardados == []


def test_un_usuario_sin_contrasena_se_trata_como_credenciales_malas() -> None:
    usuario = _usuario(password_hash="")
    repositorio = RepositorioSimulado(usuario)

    with pytest.raises(InvalidCredentialsError) as error:
        _login(repositorio, usuario.email, CONTRASENA)

    assert error.value.failed_attempts == 0
    assert repositorio.intentos_guardados == []


# --- Contador de intentos fallidos -------------------------------------------------


def test_una_contrasena_incorrecta_suma_un_intento() -> None:
    usuario = _usuario(failed_login_attempts=0)
    repositorio = RepositorioSimulado(usuario)

    with pytest.raises(InvalidCredentialsError) as error:
        _login(repositorio, usuario.email, "otra-contrasena")

    assert error.value.failed_attempts == 1
    assert error.value.offer_password_recovery is False
    assert repositorio.intentos_guardados == [1]


def test_al_llegar_al_maximo_de_intentos_se_ofrece_recuperar_la_contrasena() -> None:
    maximo = settings.max_failed_login_attempts
    usuario = _usuario(failed_login_attempts=0)
    repositorio = RepositorioSimulado(usuario)

    ofertas = []
    for _ in range(maximo):
        with pytest.raises(InvalidCredentialsError) as error:
            _login(repositorio, usuario.email, "otra-contrasena")
        ofertas.append(error.value.offer_password_recovery)

    assert repositorio.intentos_guardados == list(range(1, maximo + 1))
    assert ofertas == [False] * (maximo - 1) + [True]


def test_pasado_el_maximo_se_sigue_ofreciendo_la_recuperacion() -> None:
    maximo = settings.max_failed_login_attempts
    usuario = _usuario(failed_login_attempts=maximo)
    repositorio = RepositorioSimulado(usuario)

    with pytest.raises(InvalidCredentialsError) as error:
        _login(repositorio, usuario.email, "otra-contrasena")

    assert error.value.failed_attempts == maximo + 1
    assert error.value.offer_password_recovery is True


# --- Cuenta inactiva -----------------------------------------------------------------


def test_una_cuenta_inactiva_con_contrasena_correcta_se_rechaza() -> None:
    usuario = _usuario(is_active=False, failed_login_attempts=2)
    repositorio = RepositorioSimulado(usuario)

    with pytest.raises(InactiveAccountError):
        _login(repositorio, usuario.email, CONTRASENA)

    # No se reinicia el contador: la cuenta no llegó a iniciar sesión.
    assert repositorio.intentos_guardados == []
    assert usuario.failed_login_attempts == 2


# --- Inicio de sesión correcto -------------------------------------------------------


def test_un_inicio_de_sesion_correcto_reinicia_el_contador() -> None:
    usuario = _usuario(failed_login_attempts=2)
    repositorio = RepositorioSimulado(usuario)

    token, cargado = _login(repositorio, usuario.email, CONTRASENA)

    assert repositorio.intentos_guardados == [0]
    assert cargado is usuario
    carga = decode_access_token(token)
    assert carga.user_id == usuario.id
    assert carga.roles == ("support_agent",)


def test_sin_intentos_previos_no_se_escribe_el_contador() -> None:
    usuario = _usuario(failed_login_attempts=0)
    repositorio = RepositorioSimulado(usuario)

    _login(repositorio, usuario.email, CONTRASENA)

    assert repositorio.intentos_guardados == []
