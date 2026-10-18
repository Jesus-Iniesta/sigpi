"""Excepciones de dominio y manejadores globales de errores (S3-01).
Todas las respuestas de error de la API tienen la forma:
    {"detail": <mensaje o lista de errores>, "code": "<codigo_estable>", "request_id": "<id>"}
 `code` es un identificador estable para que el cliente decida qué hacer sin
depender del texto, y `request_id` permite ubicar el error en el registro de eventos.
"""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, log_event

logger = get_logger("errors")

INTERNAL_ERROR_MESSAGE = "Ocurrió un error interno. Intenta de nuevo más tarde."


class SigpiError(Exception):
    """Base de los errores esperados del sistema.

    Los servicios pueden lanzar una subclase y el manejador global la convierte en una
    respuesta HTTP, sin que cada router tenga que repetir `try/except` + `HTTPException`.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "sigpi_error"
    default_message: str = "No se pudo completar la operación."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class NotFoundError(SigpiError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    default_message = "El recurso solicitado no existe."


class ConflictError(SigpiError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    default_message = "La operación entra en conflicto con el estado actual del recurso."


class BusinessRuleError(SigpiError):
    """Se violó una regla de negocio (RN-xx) aunque los datos tengan el formato correcto."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "business_rule_violation"
    default_message = "La operación incumple una regla de negocio."


class AuthenticationError(SigpiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"
    default_message = "Debes iniciar sesión para continuar."


class PermissionDeniedError(SigpiError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    default_message = "No tienes permiso para realizar esta acción."


# Código estable para errores de HTTP que lanzan FastAPI/Starlette o los routers actuales.
_HTTP_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthenticated",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "unprocessable_entity",
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def error_response(
    request: Request,
    status_code: int,
    detail: object,
    code: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Construye el cuerpo uniforme de error."""
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "code": code, "request_id": _request_id(request)},
        headers=headers,
    )


async def _handle_sigpi_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, SigpiError)
    log_event(
        logger,
        "domain_error",
        level="WARNING",
        code=exc.code,
        status_code=exc.status_code,
        path=request.url.path,
        request_id=_request_id(request),
    )
    return error_response(request, exc.status_code, exc.message, exc.code)


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    # Se conservan los encabezados (p. ej. WWW-Authenticate en un 401).
    return error_response(request, exc.status_code, exc.detail, code, headers=exc.headers)


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        jsonable_encoder(exc.errors()),
        "validation_error",
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Aquí sí se guarda el rastro completo, pero al cliente solo se le da un mensaje genérico
    # y el request_id: nunca se expone el detalle interno (rutas, SQL, secretos).
    request_id = _request_id(request)
    logger.error(
        "unhandled_exception",
        exc_info=exc,
        extra={"fields": {"path": request.url.path, "request_id": request_id}},
    )
    return error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        INTERNAL_ERROR_MESSAGE,
        "internal_error",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registra los manejadores globales; se llama una sola vez al crear la aplicación."""
    app.add_exception_handler(SigpiError, _handle_sigpi_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
