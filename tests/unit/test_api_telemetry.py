"""Unit tests for redacted, structured HTTP telemetry."""

from __future__ import annotations

import asyncio
import json
import logging
from io import StringIO
from typing import cast

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pipeline_rca.api.telemetry import (
    JsonLineFormatter,
    RequestTelemetryMiddleware,
    safe_request_id,
)


def _scope(request_id: str = "request-123") -> Scope:
    return cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/health/live",
            "raw_path": b"/health/live",
            "query_string": b"secret=query-token",
            "root_path": "",
            "headers": [(b"x-request-id", request_id.encode())],
            "client": ("127.0.0.1", 1234),
            "server": ("127.0.0.1", 8000),
        },
    )


def test_request_id_rejects_control_characters_and_unbounded_values() -> None:
    assert safe_request_id("safe-ID_1.2") == "safe-ID_1.2"
    assert safe_request_id("bad\ninjected") != "bad\ninjected"
    assert safe_request_id("x" * 65) != "x" * 65


def test_json_formatter_writes_one_json_object_per_record() -> None:
    record = logging.LogRecord("test", logging.INFO, "", 1, "event", (), None)
    record.event_payload = {"event": "http.request", "status_code": 200}
    rendered = JsonLineFormatter().format(record)

    assert json.loads(rendered) == {"event": "http.request", "status_code": 200}


def test_http_telemetry_includes_correlation_and_excludes_query_secret(
    monkeypatch,
) -> None:
    import pipeline_rca.api.telemetry as telemetry

    captured = StringIO()
    handler = logging.StreamHandler(captured)
    handler.setFormatter(JsonLineFormatter())
    logger = logging.getLogger("pipeline_rca.telemetry")
    original_handlers = logger.handlers[:]
    original_propagate = logger.propagate
    logger.handlers = [handler]
    logger.propagate = False
    monkeypatch.setattr(telemetry, "configure_telemetry_logging", lambda: logger)

    async def scenario() -> tuple[list[Message], dict]:
        sent: list[Message] = []

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            scope["state"]["principal_subject"] = "operator-a"
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok", "more_body": False})

        async def receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: Message) -> None:
            sent.append(message)

        await RequestTelemetryMiddleware(cast(ASGIApp, app))(_scope(), receive, send)
        events = [json.loads(line) for line in captured.getvalue().splitlines()]
        return sent, events[-1]

    try:
        sent, event = asyncio.run(scenario())
    finally:
        logger.handlers = original_handlers
        logger.propagate = original_propagate

    headers = dict(sent[0]["headers"])
    assert headers[b"x-request-id"] == b"request-123"
    assert event["request_id"] == "request-123"
    assert event["subject"] == "operator-a"
    assert event["status_code"] == 200
    assert event["event"] == "http.request"
    assert "secret=query-token" not in captured.getvalue()
    assert "authorization" not in event
