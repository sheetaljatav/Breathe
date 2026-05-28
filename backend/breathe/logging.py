"""
Structured logging configuration.

structlog renders every log line as a single JSON object on stdout, including
the request_id that RequestIdMiddleware bound to the context for the current
request. This lets us correlate a Sentry error, an audit_log row, and an HTTP
access log line through a single ID.
"""

from __future__ import annotations

import logging

import structlog

LOGGING_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.processors.JSONRenderer(),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django.db.backends": {"level": "WARNING"},   # quiet SQL logs by default
        "celery": {"level": "INFO"},
    },
}


def configure_structlog() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name) if name else structlog.get_logger()


__all__ = ("LOGGING_CONFIG", "configure_structlog", "get_logger")


# Silence the noisy "no handlers" warning if anyone imports structlog before
# Django finishes setup.
logging.getLogger().addHandler(logging.NullHandler())
