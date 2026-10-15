"""ASGI middleware that bounds investigation request bodies before JSON parsing."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyLimitMiddleware:
    """Buffer only a bounded investigation body and reject oversized requests early."""

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        if (
            isinstance(max_body_bytes, bool)
            or not isinstance(max_body_bytes, int)
            or max_body_bytes < 1
        ):
            raise ValueError("max_body_bytes must be a positive integer")
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": f"request body exceeds {self.max_body_bytes} bytes"},
        )
        await response(scope, receive, send)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Apply the body limit only to the incident-investigation POST route."""
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/v1/investigations"
        ):
            await self.app(scope, receive, send)
            return

        content_length = next(
            (
                value
                for name, value in scope.get("headers", [])
                if name.lower() == b"content-length"
            ),
            None,
        )
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = -1
            if declared_length > self.max_body_bytes:
                await self._reject(scope, receive, send)
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue

            body.extend(message.get("body", b""))
            if len(body) > self.max_body_bytes:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        captured_body = bytes(body)
        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {
                    "type": "http.request",
                    "body": captured_body,
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)
