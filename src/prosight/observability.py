"""Structured, privacy-aware diagnostic logging for ProSight query flows."""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LOGGER_NAME = "prosight"
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Z0-9._~+/=-]+")
_SECRET = re.compile(
    r"(?i)(authorization|api[_ -]?key)\s*[:=]\s*[\"']?([^\s,\"']+)"
)


def _integer_setting(name: str, default: int, minimum: int = 1) -> int:
    """Read a positive integer setting without allowing bad config to break startup."""
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def sanitize(value: Any, limit: int | None = None) -> str:
    """Return a bounded preview with credentials and contact details redacted."""
    preview_limit = limit or _integer_setting("PROSIGHT_LOG_PREVIEW_CHARS", 160)
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            value = str(type(value).__name__)
    value = _EMAIL.sub("[REDACTED_EMAIL]", value)
    value = _PHONE.sub(
        lambda match: (
            "[REDACTED_PHONE]"
            if len(re.sub(r"\D", "", match.group(0))) >= 9
            else match.group(0)
        ),
        value,
    )
    value = _BEARER.sub("Bearer [REDACTED_SECRET]", value)
    value = _SECRET.sub(lambda match: f"{match.group(1)}=[REDACTED_SECRET]", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value if len(value) <= preview_limit else f"{value[:preview_limit]}…"


class JsonFormatter(logging.Formatter):
    """Serialize log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(getattr(record, "event_data", {}))
        if record.exc_info:
            # Log exception type only; raw tracebacks can contain sensitive payloads.
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(force: bool = False) -> logging.Logger:
    """Configure console and rotating-file handlers exactly once."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers and not force:
        return logger
    if force:
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
    level_name = os.environ.get("PROSIGHT_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False
    formatter = JsonFormatter()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    try:
        configured_dir = Path(os.environ.get("PROSIGHT_LOG_DIR", "logs"))
        log_dir = configured_dir if configured_dir.is_absolute() else ROOT / configured_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        rotating = RotatingFileHandler(
            log_dir / "prosight.log",
            maxBytes=_integer_setting("PROSIGHT_LOG_MAX_BYTES", 5 * 1024 * 1024),
            backupCount=_integer_setting("PROSIGHT_LOG_BACKUP_COUNT", 5),
            encoding="utf-8",
        )
        rotating.setFormatter(formatter)
        logger.addHandler(rotating)
    except Exception as error:
        # Logging must never make the application unavailable.
        logger.warning(
            "file_logging_unavailable",
            extra={"event_data": {
                "event": "file_logging_unavailable",
                "error_type": type(error).__name__,
            }},
        )
    return logger


@dataclass
class RequestTrace:
    """Correlation context shared by the API, provider, and tool lifecycle."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: float = field(default_factory=time.perf_counter)
    logger: logging.Logger = field(default_factory=configure_logging, repr=False)

    @property
    def duration_ms(self) -> int:
        """Return elapsed request time in milliseconds."""
        return round((time.perf_counter() - self.started_at) * 1000)

    def event(self, name: str, level: int = logging.INFO, **fields: Any) -> None:
        """Emit a safe structured event; failures are intentionally swallowed."""
        try:
            data = {
                "event": name,
                "request_id": self.request_id,
                "duration_ms": self.duration_ms,
            }
            data.update(fields)
            self.logger.log(level, name, extra={"event_data": data})
        except Exception:
            return
