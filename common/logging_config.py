"""Shared structured (JSON-lines) logging for ingestion and backend.

Every service in this project logs one JSON object per line to stdout so logs
are grep-able locally and machine-parseable if shipped anywhere later. Extra
fields passed via ``logger.info("msg", extra={"rows": 42})`` are merged into
the JSON payload.
"""

import json
import logging
import sys
from datetime import UTC, datetime

# logging.LogRecord attributes that are not user-supplied "extra" fields.
_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger. Idempotent."""
    root = logging.getLogger()
    root.setLevel(level)
    for handler in root.handlers:
        if getattr(handler, "_news_buzz_globe", False):
            return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._news_buzz_globe = True  # type: ignore[attr-defined]
    root.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
