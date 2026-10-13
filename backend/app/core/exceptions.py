"""Excepciones de negocio y manejo transversal de errores (S3-01).

Los servicios lanzan subclases de `SigpiError`; el manejador global las traduce a
HTTP con un formato uniforme, de modo que los routers ya no necesitan un
`try/except` por caso de uso:

    {"detail": "<mensaje o lista de errores>", "code": "<código estable>", "request_id": "<id>"}

`detail` conserva el mismo significado que en FastAPI, por lo que el cliente del
frontend (`apiFetch`) y las pruebas existentes siguen funcionando sin cambios.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app.core.logging import get_logger, log_event, request_id_var

_logger = get_logger("errors")


class SigpiError(Exception):
    """Base de las excepciones de negocio; cada subclase fija su código HTTP."""

    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "Error interno del servidor."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        if code is not None:
            self.code = code
        self.extra = extra or {}
        super().__init__(self.message)


class BusinessRuleError(SigpiError):
    status_code = 422
    code = "business_rule_violation"
    default_message = "La operación incumple una regla de negocio."


class NotFoundError(SigpiError):
    status_code = 404
    code = "not_found"
    default_message = "El recurso solicitado no existe."


class ConflictError(SigpiError):
    status_code = 409
    code = "conflict"
    default_message = "La operación entra en conflicto con el estado actual."


class AuthenticationError(SigpiError):
    status_code = 401
    code = "authentication_failed"
    default_message = "Credenciales inválidas."


class PermissionDeniedError(SigpiError):
    status_code = 403
    code = "permission_denied"
    default_message = "No tiene permiso para realizar esta operación."


class ServiceUnavailableError(SigpiError):
    """Un sistema externo (directorio, correo, clasificador) no respondió."""

    status_code = 503
    code = "external_service_unavailable"
    default_message = "Un servicio externo no está disponible."


def build_error_body(
    *, detail: Any, code: str, request_id: str | None, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"detail": detail, "code": code, "request_id": request_id}
    if extra:
        body["extra"] = extra
    return body


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None) or request_id_var.get()


async def _sigpi_error_handler(request: Request, exc: SigpiError) -> JSONResponse:
    log_event(
        _logger,
        "error.domain",
        level=logging.ERROR if exc.status_code >= 500 else logging.WARNING,
        code=exc.code,
        status=exc.status_code,
        path=request.url.path,
        error_message=exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_body(
            detail=exc.message, code=exc.code, request_id=_request_id(request), extra=exc.extra
        ),
    )


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    log_event(
        _logger,
        "error.request_validation",
        level=logging.WARNING,
        status=422,
        path=request.url.path,
        fields=[".".join(str(part) for part in error["loc"]) for error in exc.errors()],
    )
    return JSONResponse(
        status_code=422,
        content=build_error_body(
            detail=jsonable_encoder(exc.errors()),
            code="request_validation_error",
            request_id=_request_id(request),
        ),
    )


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    if exc.status_code < 200 or exc.status_code in (204, 304):
        return Response(status_code=exc.status_code, headers=exc.headers)
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_body(
            detail=exc.detail, code=f"http_{exc.status_code}", request_id=_request_id(request)
        ),
        headers=exc.headers,
    )


async def _integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    _logger.warning(
        "error.integrity",
        extra={"event": "error.integrity", "path": request.url.path},
        exc_info=exc,
    )
    return JSONResponse(
        status_code=409,
        content=build_error_body(
            detail="La operación entra en conflicto con datos existentes.",
            code="integrity_error",
            request_id=_request_id(request),
        ),
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    _logger.error(
        "error.unhandled",
        extra={"event": "error.unhandled", "path": request.url.path},
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content=build_error_body(
            detail="Error interno del servidor.",
            code="internal_error",
            request_id=_request_id(request),
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Instala el manejo uniforme de errores en la aplicación."""
    app.add_exception_handler(SigpiError, _sigpi_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(IntegrityError, _integrity_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
