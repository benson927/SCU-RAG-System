import contextvars
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone


request_id_context = contextvars.ContextVar("request_id", default=None)
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def normalize_request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    if candidate and REQUEST_ID_RE.fullmatch(candidate):
        return candidate
    return str(uuid.uuid4())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        for key in ("method", "path", "status_code", "duration_ms", "job_id", "object_key"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
