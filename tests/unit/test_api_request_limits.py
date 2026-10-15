"""Unit tests for the streaming ASGI request-body limit."""

from __future__ import annotations

import asyncio
from typing import cast

from starlette.types import ASGIApp, Message, Scope, Send

from pipeline_rca.api.request_limits import RequestBodyLimitMiddleware


def _scope(headers: list[tuple[bytes, bytes]] | None = None) -> Scope:
    return cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/v1/investigations",
            "raw_path": b"/v1/investigations",
            "query_string": b"",
            "root_path": "",
            "headers": headers or [],
            "client": ("test-client", 12345),
            "server": ("test-server", 8000),
        },
    )


def test_declared_oversized_body_is_rejected_before_receiving_body() -> None:
    async def scenario() -> tuple[list[Message], bool]:
        sent: list[Message] = []
        app_called = False

        async def app(scope: Scope, receive, send: Send) -> None:
            nonlocal app_called
            app_called = True

        async def receive() -> Message:
            raise AssertionError("the middleware should reject from Content-Length")

        async def send(message: Message) -> None:
            sent.append(message)

        middleware = RequestBodyLimitMiddleware(
            cast(ASGIApp, app),
            max_body_bytes=128,
        )
        await middleware(_scope([(b"content-length", b"129")]), receive, send)
        return sent, app_called

    sent, app_called = asyncio.run(scenario())

    assert not app_called
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    assert b"request body exceeds 128 bytes" in sent[1]["body"]


def test_streaming_body_without_content_length_is_rejected_at_limit() -> None:
    async def scenario() -> tuple[list[Message], bool, int]:
        sent: list[Message] = []
        app_called = False
        incoming = [
            {"type": "http.request", "body": b"a" * 100, "more_body": True},
            {"type": "http.request", "body": b"b" * 40, "more_body": True},
        ]
        received = 0

        async def app(scope: Scope, receive, send: Send) -> None:
            nonlocal app_called
            app_called = True

        async def receive() -> Message:
            nonlocal received
            received += 1
            return cast(Message, incoming.pop(0))

        async def send(message: Message) -> None:
            sent.append(message)

        middleware = RequestBodyLimitMiddleware(
            cast(ASGIApp, app),
            max_body_bytes=128,
        )
        await middleware(_scope(), receive, send)
        return sent, app_called, received

    sent, app_called, received = asyncio.run(scenario())

    assert not app_called
    assert received == 2
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


def test_bounded_streaming_body_is_replayed_intact_to_application() -> None:
    async def scenario() -> tuple[bytes, list[Message]]:
        sent: list[Message] = []
        delivered = b""
        incoming = [
            {"type": "http.request", "body": b"hello", "more_body": True},
            {"type": "http.request", "body": b" world", "more_body": False},
        ]

        async def receive() -> Message:
            return cast(Message, incoming.pop(0))

        async def app(scope: Scope, receive, send: Send) -> None:
            nonlocal delivered
            message = await receive()
            delivered = message.get("body", b"")
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"ok",
                    "more_body": False,
                }
            )

        async def send(message: Message) -> None:
            sent.append(message)

        middleware = RequestBodyLimitMiddleware(cast(ASGIApp, app), max_body_bytes=128)
        await middleware(_scope(), receive, send)
        return delivered, sent

    delivered, sent = asyncio.run(scenario())

    assert delivered == b"hello world"
    assert sent[0]["status"] == 200
