"""Pruebas del manejo transversal de errores y del registro estructurado (S3-01).

No necesitan base de datos: montan una aplicación mínima con el middleware y los
manejadores reales de `app.core`.
"""

import json
import logging

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
    SigpiError,
    register_exception_handlers,
)
from app.core.logging import (
    REQUEST_ID_HEADER,
    JsonFormatter,
    RequestContextMiddleware,
    log_event,
    request_id_var,
    setup_logging,
)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/ok")
    async def ok() -> dict[str, str | None]:
        return {"request_id": request_id_var.get()}

    @app.get("/no-existe")
    async def no_existe() -> None:
        raise NotFoundError("La solicitud SIG-0099 no existe.")

    @app.get("/conflicto")
    async def conflicto() -> None:
        raise ConflictError("La cuenta ya está registrada.")

    @app.get("/regla")
    async def regla() -> None:
        raise BusinessRuleError("La descripción es demasiado corta.", extra={"min": 30})

    @app.get("/permiso")
    async def permiso() -> None:
        raise PermissionDeniedError()

    @app.get("/directorio")
    async def directorio() -> None:
        raise ServiceUnavailableError("El directorio no responde.")

    @app.get("/http")
    async def http_error() -> None:
        raise HTTPException(status_code=403, detail="Acceso restringido.")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secreto-interno-no-debe-salir")

    @app.get("/items/{number}")
    async def item(number: int) -> dict[str, int]:
        return {"number": number}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    level = root.level
    yield
    for handler in list(root.handlers):
        if getattr(handler, "_sigpi_handler", False):
            root.removeHandler(handler)
    root.setLevel(level)


# --- formato uniforme de error --------------------------------------------------
@pytest.mark.parametrize(
    ("path", "status", "code", "detail"),
    [
        ("/no-existe", 404, "not_found", "La solicitud SIG-0099 no existe."),
        ("/conflicto", 409, "conflict", "La cuenta ya está registrada."),
        ("/regla", 422, "business_rule_violation", "La descripción es demasiado corta."),
        ("/permiso", 403, "permission_denied", PermissionDeniedError.default_message),
        ("/directorio", 503, "external_service_unavailable", "El directorio no responde."),
    ],
)
def test_error_de_negocio_responde_con_formato_uniforme(client, path, status, code, detail) -> None:
    response = client.get(path)

    assert response.status_code == status
    body = response.json()
    assert body["detail"] == detail
    assert body["code"] == code
    assert body["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_error_de_negocio_puede_llevar_datos_adicionales(client) -> None:
    assert client.get("/regla").json()["extra"] == {"min": 30}


def test_toda_excepcion_de_negocio_hereda_de_sigpi_error() -> None:
    for error in (BusinessRuleError, NotFoundError, ConflictError, ServiceUnavailableError):
        assert issubclass(error, SigpiError)


def test_http_exception_conserva_su_detalle_y_agrega_codigo(client) -> None:
    response = client.get("/http")

    assert response.status_code == 403
    assert response.json()["detail"] == "Acceso restringido."
    assert response.json()["code"] == "http_403"


def test_ruta_inexistente_responde_404_con_formato_uniforme(client) -> None:
    response = client.get("/ruta-que-no-existe")

    assert response.status_code == 404
    assert response.json()["code"] == "http_404"
    assert response.json()["request_id"]


def test_validacion_de_entrada_conserva_la_lista_de_errores_de_fastapi(client) -> None:
    response = client.get("/items/no-es-un-numero")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "request_validation_error"
    assert isinstance(body["detail"], list)
    assert body["detail"][0]["loc"][-1] == "number"


def test_error_inesperado_responde_500_sin_filtrar_detalles_internos(caplog) -> None:
    safe_client = TestClient(_build_app(), raise_server_exceptions=False)
    caplog.set_level(logging.ERROR, logger="sigpi.errors")

    response = safe_client.get("/boom")

    assert response.status_code == 500
    assert "secreto-interno" not in response.text
    assert response.json()["code"] == "internal_error"
    assert response.json()["request_id"]
    registro = [r for r in caplog.records if r.name == "sigpi.errors"]
    assert registro, "el error inesperado debe quedar en el registro"
    assert registro[0].exc_info is not None


# --- identificador de petición --------------------------------------------------
def test_cada_peticion_recibe_un_identificador_distinto(client) -> None:
    first = client.get("/ok").headers[REQUEST_ID_HEADER]
    second = client.get("/ok").headers[REQUEST_ID_HEADER]

    assert first and second and first != second


def test_el_identificador_esta_disponible_dentro_del_caso_de_uso(client) -> None:
    response = client.get("/ok")

    assert response.json()["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_se_respeta_el_identificador_enviado_por_el_cliente(client) -> None:
    response = client.get("/ok", headers={REQUEST_ID_HEADER: "front-abc-123"})

    assert response.headers[REQUEST_ID_HEADER] == "front-abc-123"


def test_se_descarta_un_identificador_con_caracteres_peligrosos(client) -> None:
    response = client.get("/ok", headers={REQUEST_ID_HEADER: "a b;{injection}"})

    assert response.headers[REQUEST_ID_HEADER] != "a b;{injection}"
    assert response.headers[REQUEST_ID_HEADER]


# --- registro estructurado ------------------------------------------------------
def test_cada_peticion_deja_un_evento_con_metodo_ruta_estatus_y_duracion(client, caplog) -> None:
    caplog.set_level(logging.INFO, logger="sigpi.request")

    client.get("/ok")

    eventos = [r for r in caplog.records if getattr(r, "event", "") == "request.completed"]
    assert len(eventos) == 1
    evento = eventos[0]
    assert (evento.method, evento.path, evento.status) == ("GET", "/ok", 200)
    assert evento.duration_ms >= 0


def test_json_formatter_produce_una_linea_json_con_los_campos_adicionales() -> None:
    logger = logging.getLogger("sigpi.prueba")
    record = logger.makeRecord(
        "sigpi.prueba", logging.INFO, __file__, 1, "solicitud %s creada", ("SIG-0001",), None
    )
    record.event = "solicitud.creada"
    record.folio = "SIG-0001"
    record.request_id = "abc123"

    linea = JsonFormatter().format(record)

    datos = json.loads(linea)
    assert "\n" not in linea
    assert datos["message"] == "solicitud SIG-0001 creada"
    assert datos["level"] == "INFO"
    assert datos["logger"] == "sigpi.prueba"
    assert datos["request_id"] == "abc123"
    assert datos["event"] == "solicitud.creada"
    assert datos["folio"] == "SIG-0001"
    assert datos["timestamp"].endswith("+00:00")


def test_json_formatter_incluye_la_traza_de_una_excepcion() -> None:
    logger = logging.getLogger("sigpi.prueba")
    try:
        raise ValueError("falla controlada")
    except ValueError as exc:
        info = (type(exc), exc, exc.__traceback__)
        record = logger.makeRecord("sigpi.prueba", logging.ERROR, __file__, 1, "falló", (), info)

    datos = json.loads(JsonFormatter().format(record))

    assert "ValueError: falla controlada" in datos["exception"]


def test_log_event_agrega_campos_y_renombra_los_que_chocan_con_logrecord(caplog) -> None:
    logger = logging.getLogger("sigpi.prueba")
    caplog.set_level(logging.INFO, logger="sigpi.prueba")

    log_event(logger, "demo.evento", folio="SIG-0002", name="choca-con-logrecord")

    record = caplog.records[-1]
    assert record.event == "demo.evento"
    assert record.folio == "SIG-0002"
    assert record.name_ == "choca-con-logrecord"
    assert record.name == "sigpi.prueba"


def test_setup_logging_es_idempotente(restore_logging) -> None:
    setup_logging("INFO", json_format=True)
    setup_logging("DEBUG", json_format=False)

    propios = [h for h in logging.getLogger().handlers if getattr(h, "_sigpi_handler", False)]
    assert len(propios) == 1
    assert logging.getLogger().level == logging.DEBUG
