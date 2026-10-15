"""Structured JSON request telemetry with explicit secret and payload redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_LOGGER_NAME = "pipeline_rca.telemetry"


class JsonLineHandler(logging.StreamHandler[Any]):
    """Stream handler identifiable without untyped custom LogRecord attributes."""

    _pipeline_rca_json = True


class JsonLineFormatter(logging.Formatter):
    """Render telemetry log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event_payload", None)
        if not isinstance(event, dict):
            event = {"event": record.getMessage(), "level": record.levelname.lower()}
        return json.dumps(event, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def configure_telemetry_logging() -> logging.Logger:
    """Configure an isolated JSON-lines logger without changing the application's root logger."""
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(isinstance(handler, JsonLineHandler) for handler in logger.handlers):
        handler = JsonLineHandler(sys.stdout)
        handler.setFormatter(JsonLineFormatter())
        logger.addHandler(handler)
    return logger


def safe_request_id(value: str | None) -> str:
    """Accept a bounded opaque request id; otherwise generate a UUID."""
    if value and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return str(uuid.uuid4())


def emit_telemetry(event: dict[str, Any]) -> None:
    """Emit a bounded, structured event; callers must not include secrets or request bodies."""
    logger = configure_telemetry_logging()
    safe_event = {
        "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
        **event,
    }
    logger.info("http.request", extra={"event_payload": safe_event})


class RequestTelemetryMiddleware:
    """Log request lifecycle metadata only, never query strings, headers, or bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        supplied_id = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        request_id = safe_request_id(supplied_id)
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        started = time.perf_counter()
        status_code = 500
        route = str(scope.get("path", "/"))[:160]

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                outgoing = list(message.get("headers", []))
                outgoing.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": outgoing}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            emit_telemetry(
                {
                    "event": "http.request",
                    "request_id": request_id,
                    "method": scope.get("method", "UNKNOWN"),
                    "route": route,
                    "status_code": 500,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "outcome": "exception",
                    "subject": state.get("principal_subject", "anonymous"),
                }
            )
            raise
        emit_telemetry(
            {
                "event": "http.request",
                "request_id": request_id,
                "method": scope.get("method", "UNKNOWN"),
                "route": route,
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "outcome": "success" if status_code < 500 else "error",
                "subject": state.get("principal_subject", "anonymous"),
            }
        )
