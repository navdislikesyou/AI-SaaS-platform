"""Request-scoped middleware."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import (
    new_request_id,
    reset_request_id,
    set_request_id,
)

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id to each request and log its outcome.

    An inbound ``X-Request-ID`` is reused when present so that a correlation
    id set by an upstream proxy or the frontend survives end to end.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Assign a request id, log timing, and stamp the response header.

        Args:
            request: The incoming request.
            call_next: The next handler in the middleware chain.

        Returns:
            The response, with the request id header attached.
        """
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        token = set_request_id(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "request method=%s path=%s status=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
            )
            reset_request_id(token)
