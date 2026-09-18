"""Structured logging with per-request correlation IDs (Sections 33, 49)."""

import contextvars
import json
import logging
import sys
import time
import uuid

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "request_id": request_id_var.get(),
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            payload.update(record.extra_data)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # Quiet noisy libraries.
    for noisy in ("httpx", "chromadb", "urllib3", "google"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def new_request_id() -> str:
    rid = uuid.uuid4().hex[:12]
    request_id_var.set(rid)
    return rid


def log_event(message: str, **fields) -> None:
    logging.getLogger("docmind").info(message, extra={"extra_data": fields})
