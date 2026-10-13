"""Registro estructurado de eventos y contexto de petición (S3-01).

- `setup_logging` configura un único manejador en la raíz: JSON (por defecto) o texto.
- `RequestContextMiddleware` asigna un identificador a cada petición (cabecera
  `X-Request-ID`), lo deja disponible en `request_id_var` y registra su resultado.
- `log_event` emite eventos con campos estructurados sin repetir el formato.
"""

import json
import logging
import re
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_HANDLER_MARK = "_sigpi_handler"
_TEXT_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"

# Atributos propios de LogRecord: no se copian como campos adicionales al JSON.
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
    "request_id",
}


class RequestIdFilter(logging.Filter):
    """Agrega a cada registro el identificador de la petición en curso."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """Una línea JSON por registro, con los campos adicionales de `extra`."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class _StdoutHandler(logging.StreamHandler):
    """Escribe siempre en el `sys.stdout` vigente (útil con la captura de pytest)."""

    def __init__(self) -> None:
        super().__init__(sys.stdout)

    @property
    def stream(self):  # type: ignore[override]
        return sys.stdout

    @stream.setter
    def stream(self, value) -> None:
        pass


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configura el registro de la aplicación; es seguro llamarla más de una vez."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARK, False):
            root.removeHandler(handler)

    handler = _StdoutHandler()
    setattr(handler, _HANDLER_MARK, True)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JsonFormatter() if json_format else logging.Formatter(_TEXT_FORMAT))
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"sigpi.{name}")


def log_event(
    logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: Any
) -> None:
    """Emite un evento con campos estructurados: `log_event(log, "solicitud.creada", folio=f)`."""
    safe = {(f"{key}_" if key in _RESERVED else key): value for key, value in fields.items()}
    logger.log(level, event, extra={"event": event, **safe})


def _request_id_from(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name == REQUEST_ID_HEADER.lower().encode():
            candidate = value.decode("latin-1")
            if _VALID_REQUEST_ID.fullmatch(candidate):
                return candidate
    return uuid.uuid4().hex


class RequestContextMiddleware:
    """Middleware ASGI: identificador por petición, cabecera de respuesta y bitácora."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._logger = get_logger("request")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id_from(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", [])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            log_event(
                self._logger,
                "request.completed",
                level=logging.ERROR if status_code >= 500 else logging.INFO,
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            request_id_var.reset(token)
