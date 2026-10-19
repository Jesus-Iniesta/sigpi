"""Pruebas del manejo de errores y del registro de eventos (S3-01).

No usan base de datos: Se arma una aplicación mínima con rutas que fallan a propósito.
"""

import json
import logging

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.exceptions import (
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    register_exception_handlers,
)
from app.core.logging import (
    JsonFormatter,
    RequestContextMiddleware,
    configure_logging,
    get_logger,
    log_event,
)

SECRETO = "postgresql://usuario:clave-super-secreta@localhost/sigpi"


class _Item(BaseModel):
    nombre: str


class _ListHandler(logging.Handler):
    """Guarda cada línea del registro ya formateada como JSON."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(json.loads(self.format(record)))


@pytest.fixture
def logs():
    configure_logging("INFO")
    handler = _ListHandler()
    logging.getLogger("sigpi").addHandler(handler)
    yield handler.lines
    logging.getLogger("sigpi").removeHandler(handler)


@pytest.fixture
def client(logs) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/no-encontrado")
    async def no_encontrado():
        raise NotFoundError("La solicitud SIG-0099 no existe.")

    @app.get("/conflicto")
    async def conflicto():
        raise ConflictError()

    @app.get("/regla")
    async def regla():
        raise BusinessRuleError("La prioridad no se puede editar directamente.")

    @app.get("/sin-sesion")
    async def sin_sesion():
        raise AuthenticationError()

    @app.get("/prohibido")
    async def prohibido():
        raise PermissionDeniedError()

    @app.get("/http-401")
    async def http_401():
        raise HTTPException(
            status_code=401,
            detail="Debes iniciar sesión para continuar.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.post("/items")
    async def items(item: _Item):
        return item

    @app.get("/falla")
    async def falla():
        raise RuntimeError(SECRETO)

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    return TestClient(app, raise_server_exceptions=False)


# --- Excepciones de dominio ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("ruta", "estatus", "codigo"),
    [
        ("/no-encontrado", 404, "not_found"),
        ("/conflicto", 409, "conflict"),
        ("/regla", 422, "business_rule_violation"),
        ("/sin-sesion", 401, "unauthenticated"),
        ("/prohibido", 403, "forbidden"),
    ],
)
def test_excepcion_de_dominio_usa_el_formato_uniforme(client, ruta, estatus, codigo):
    response = client.get(ruta)

    assert response.status_code == estatus
    body = response.json()
    assert set(body) == {"detail", "code", "request_id"}
    assert isinstance(body["detail"], str) and body["detail"]
    assert body["code"] == codigo


def test_excepcion_de_dominio_conserva_el_mensaje_enviado(client):
    body = client.get("/no-encontrado").json()

    assert body["detail"] == "La solicitud SIG-0099 no existe."


def test_excepcion_sin_mensaje_usa_el_mensaje_por_defecto(client):
    body = client.get("/conflicto").json()

    assert "conflicto" in body["detail"]


# --- Errores de FastAPI que ya existían ---------------------------------------------------


def test_http_exception_conserva_detail_y_encabezados(client):
    response = client.get("/http-401")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    body = response.json()
    assert body["detail"] == "Debes iniciar sesión para continuar."
    assert body["code"] == "unauthenticated"


def test_ruta_inexistente_responde_404_uniforme(client):
    response = client.get("/no-existe")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_error_de_validacion_mantiene_detail_como_lista(client):
    response = client.post("/items", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert isinstance(body["detail"], list)
    assert body["detail"][0]["loc"] == ["body", "nombre"]


# --- Error inesperado (500) ---------------------------------------------------------------


def test_error_inesperado_responde_500_generico_sin_filtrar_detalles(client):
    response = client.get("/falla")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "internal_error"
    assert SECRETO not in response.text
    assert "RuntimeError" not in response.text


def test_error_inesperado_deja_el_rastro_completo_en_el_registro(client, logs):
    response = client.get("/falla")

    request_id = response.json()["request_id"]
    errores = [line for line in logs if line["event"] == "unhandled_exception"]
    assert len(errores) == 1
    assert errores[0]["level"] == "ERROR"
    assert errores[0]["request_id"] == request_id
    assert "RuntimeError" in errores[0]["exception"]


# --- Identificador de petición ------------------------------------------------------------


def test_cada_respuesta_incluye_un_request_id_en_encabezado_y_cuerpo(client):
    response = client.get("/no-encontrado")

    assert response.headers["X-Request-ID"] == response.json()["request_id"]
    assert response.headers["X-Request-ID"] != "-"


def test_se_respeta_un_request_id_entrante_valido(client):
    response = client.get("/ok", headers={"X-Request-ID": "mi-id-123"})

    assert response.headers["X-Request-ID"] == "mi-id-123"


def test_se_reemplaza_un_request_id_entrante_invalido(client):
    response = client.get("/ok", headers={"X-Request-ID": "malo id\t con espacios"})

    assert response.headers["X-Request-ID"] != "malo id\t con espacios"
    assert len(response.headers["X-Request-ID"]) == 32


# --- Registro estructurado ----------------------------------------------------------------


def test_cada_peticion_registra_metodo_ruta_estatus_y_duracion(client, logs):
    response = client.get("/ok")

    eventos = [line for line in logs if line["event"] == "request_completed"]
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento["method"] == "GET"
    assert evento["path"] == "/ok"
    assert evento["status_code"] == 200
    assert evento["duration_ms"] >= 0
    assert evento["request_id"] == response.headers["X-Request-ID"]


def test_el_registro_no_incluye_la_cadena_de_consulta(client, logs):
    client.get("/ok?token=abc123")

    assert "abc123" not in json.dumps(logs)


def test_log_event_agrega_campos_estructurados(logs):
    log_event(get_logger("pruebas"), "solicitud_creada", folio="SIG-0001", canal="phone")

    evento = logs[-1]
    assert evento["event"] == "solicitud_creada"
    assert evento["logger"] == "sigpi.pruebas"
    assert evento["folio"] == "SIG-0001"
    assert evento["canal"] == "phone"
    assert evento["level"] == "INFO"
    assert "timestamp" in evento


def test_error_de_dominio_se_registra_como_advertencia(client, logs):
    client.get("/no-encontrado")

    eventos = [line for line in logs if line["event"] == "domain_error"]
    assert len(eventos) == 1
    assert eventos[0]["level"] == "WARNING"
    assert eventos[0]["code"] == "not_found"
