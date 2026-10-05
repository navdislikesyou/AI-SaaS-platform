"""Domain exceptions and centralized FastAPI exception handlers.

Every error raised anywhere in the application should be an :class:`AppError`
subclass so that a single handler can render a consistent response envelope.
Stack traces are logged server-side and never returned to clients.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for all expected application errors.

    Attributes:
        message: Human-readable, safe-to-return description.
        details: Optional structured context for the client.
        status_code: HTTP status code this error maps to.
        error_code: Stable machine-readable error identifier.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        details: Any | None = None,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize the error.

        Args:
            message: Human-readable description.
            details: Optional structured detail payload.
            status_code: Override for the default status code.
            error_code: Override for the default error code.
        """
        super().__init__(message)
        self.message = message
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code


class ValidationFailedError(AppError):
    """Raised when a request payload fails validation."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "VALIDATION_ERROR"


class UnknownAgentError(AppError):
    """Raised when a requested agent name is not registered."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "AGENT_NOT_FOUND"


class UnknownOperationError(AppError):
    """Raised when an agent does not advertise the requested operation."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "OPERATION_NOT_FOUND"


class AgentUnavailableError(AppError):
    """Raised when an agent is registered but its implementation is absent.

    This is the expected state for every agent until the real implementations
    are integrated. It maps to 503 rather than 500 because retrying later may
    succeed.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "AGENT_UNAVAILABLE"


class AgentExecutionError(AppError):
    """Raised when a connected agent fails while handling a request."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "AGENT_EXECUTION_FAILED"


class AgentTimeoutError(AppError):
    """Raised when an agent exceeds its allowed execution time."""

    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    error_code = "AGENT_TIMEOUT"


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the shared exception handlers to an application.

    Args:
        app: The FastAPI application to configure.
    """

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "app_error code=%s status=%s path=%s detail=%s",
            exc.error_code,
            exc.status_code,
            request.url.path,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(request, exc.error_code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("validation_error path=%s count=%s", request.url.path, len(exc.errors()))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                request,
                "VALIDATION_ERROR",
                "Request validation failed.",
                _safe_validation_details(exc.errors()),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                request,
                f"HTTP_{exc.status_code}",
                str(exc.detail),
                None,
            ),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception path=%s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(
                request,
                "INTERNAL_ERROR",
                "An unexpected server error occurred.",
                None,
            ),
        )


def _error_body(request: Request, code: str, message: str, details: Any | None) -> dict[str, Any]:
    """Build the standard error response payload.

    Args:
        request: The active request, used to read the correlation id.
        code: Machine-readable error code.
        message: Human-readable message safe for clients.
        details: Optional structured detail payload.

    Returns:
        A JSON-serializable error body.
    """
    from app.core.logging_config import get_request_id

    return {
        "success": False,
        "error": {"code": code, "message": message, "details": details},
        "request_id": get_request_id(),
    }


def _safe_validation_details(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """Strip non-serializable values out of Pydantic validation errors.

    Args:
        errors: Raw error entries from Pydantic.

    Returns:
        Sanitized error entries containing only loc, msg, and type.
    """
    sanitized: list[dict[str, Any]] = []
    for error in errors:
        sanitized.append(
            {
                "loc": [str(part) for part in error.get("loc", ())],
                "msg": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
        )
    return sanitized
