"""Registro estructurado de eventos (S3-01).

Cada línea del registro es un objeto JSON (una línea por evento), fácil de leer por una
persona y de filtrar por una herramienta. Todo evento generado durante una petición HTTP
incluye su `request_id`, el mismo que recibe el cliente en el encabezado `X-Request-ID`.

Qué NO se registra: contraseñas, tokens, cuerpos de petición ni cadenas de consulta.
"""

import contextvars
import json
import logging
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOGGER_ROOT = "sigpi"
REQUEST_ID_HEADER = "X-Request-ID"

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# Solo se acepta un identificador entrante "razonable": evita inyectar saltos de línea en el log.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class JsonFormatter(logging.Formatter):
    """Da formato JSON a cada registro, con los campos extra de `log_event`."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        payload.setdefault("request_id", request_id_var.get())
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configura el logger `sigpi` (idempotente: se puede llamar más de una vez)."""
    logger = logging.getLogger(LOGGER_ROOT)
    logger.setLevel(level.upper())
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger hijo de `sigpi`, p. ej. `get_logger("solicitudes")`."""
    return logging.getLogger(f"{LOGGER_ROOT}.{name}")


def log_event(logger: logging.Logger, event: str, level: str = "INFO", **fields: Any) -> None:
    """Registra un evento con nombre y datos estructurados.

    Ejemplo: `log_event(logger, "solicitud_creada", folio="SIG-0001", canal="phone")`.
    """
    logger.log(logging.getLevelName(level.upper()), event, extra={"fields": fields})


class RequestContextMiddleware:
    """Asigna un `request_id` a cada petición y registra su resultado y duración."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = get_logger("http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500  # valor por defecto si la excepción no llega a generar respuesta

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            log_event(
                self.logger,
                "request_completed",
                level="ERROR" if status_code >= 500 else "INFO",
                method=scope["method"],
                path=scope["path"],
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            request_id_var.reset(token)
