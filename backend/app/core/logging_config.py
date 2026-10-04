"""Logging configuration and per-request correlation ids.

Configures the root logger once, either as human-readable console output or
as structured JSON for log shipping. Also provides a ContextVar holding the
current request id so that log records and error bodies can be correlated.

The module is named ``logging_config`` rather than ``logging`` to avoid
shadowing the standard library module.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar, Token
from typing import Any

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the correlation id for the current request.

    Returns:
        The request id, or ``"-"`` outside a request context.
    """
    return _request_id.get()


def set_request_id(value: str) -> Token[str]:
    """Bind a request id to the current context.

    Args:
        value: The correlation id to bind.

    Returns:
        The token produced by the ContextVar, for later reset.
    """
    return _request_id.set(value)


def reset_request_id(token: Token[str]) -> None:
    """Restore a previous correlation id.

    Args:
        token: The token returned by :func:`set_request_id`.
    """
    _request_id.reset(token)


def new_request_id() -> str:
    """Generate a fresh correlation id without binding it.

    Returns:
        A new hex request id.
    """
    return uuid.uuid4().hex


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every log record.

    Attributes:
        request_id: The record attribute name that is populated.
    """

    def __init__(self, request_id: str = "request_id") -> None:
        """Initialize the filter.

        Args:
            request_id: Name of the record attribute to populate.
        """
        super().__init__()
        self.request_id = request_id

    def filter(self, record: logging.LogRecord) -> bool:
        """Inject the context request id into a log record.

        Args:
            record: The record being emitted.

        Returns:
            True so the record is always emitted.
        """
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects.

    Attributes:
        sensitive_keys: Record keys whose values are replaced with a mask.
    """

    sensitive_keys: frozenset[str] = frozenset(
        {
            "api_key",
            "apikey",
            "authorization",
            "cookie",
            "password",
            "secret",
            "token",
            "access_token",
            "refresh_token",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        """Format a record as JSON.

        Args:
            record: The record to format.

        Returns:
            A JSON string describing the record.
        """
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key in logging.LogRecord("", 0, "", 0, "", (), None).__dict__:
                continue
            if key in self.sensitive_keys:
                value = "***"
            if key in {"request_id", "msg", "args", "exc_info", "exc_text"}:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(log_level: str = "INFO", log_format: str = "console") -> None:
    """Configure root logging for the application.

    Args:
        log_level: Minimum level to emit.
        log_format: ``console`` for readable output, ``json`` for shipping.

    Raises:
        ValueError: If ``log_format`` is not a recognized value.
    """
    if log_format not in {"console", "json"}:
        raise ValueError(f"Unsupported log_format: {log_format!r}")

    if log_format == "json":
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"
        )

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    for name in ("uvicorn", "uvicorn.access"):
        target = logging.getLogger(name)
        target.handlers.clear()
        target.addHandler(handler)
        target.setLevel(log_level)
        target.propagate = False
