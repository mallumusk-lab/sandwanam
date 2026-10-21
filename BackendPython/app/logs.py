"""Structured (JSON-line) logging. Never log passwords, tokens, cookies or customer PII."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

_LOGGER = logging.getLogger("goldloan")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure() -> None:
    if _LOGGER.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    _LOGGER.addHandler(handler)
    _LOGGER.setLevel(logging.INFO)
    _LOGGER.propagate = False


def info(event: str, **fields) -> None:
    _LOGGER.info(event, extra={"fields": fields})


def warning(event: str, **fields) -> None:
    _LOGGER.warning(event, extra={"fields": fields})


def error(event: str, *, exc_info: bool = False, **fields) -> None:
    _LOGGER.error(event, exc_info=exc_info, extra={"fields": fields})
