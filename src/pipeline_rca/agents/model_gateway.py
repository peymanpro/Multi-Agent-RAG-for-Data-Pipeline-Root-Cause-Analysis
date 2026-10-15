"""Minimal chat-model protocol and OpenAI-compatible HTTP adapter."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ModelProviderError(RuntimeError):
    """Safe, provider-neutral model invocation failure."""


class ChatModel(Protocol):
    """Small interface that lets agents be tested without an external model."""

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1_000,
    ) -> str:
        """Return the assistant message content as plain text."""


class OpenAICompatibleChatModel:
    """Adapter for APIs that implement the OpenAI chat-completions contract.

    Credentials are supplied at runtime and are never included in exception messages.
    Model requests are opt-in; all deterministic core code remains usable offline.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must be non-empty")
        if not model.strip():
            raise ValueError("model must be non-empty")
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("base_url must use HTTP or HTTPS")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(
        cls, *, timeout_seconds: float = 20.0
    ) -> OpenAICompatibleChatModel:
        """Create the adapter from RCA_API_KEY, RCA_MODEL, and optional RCA_API_BASE_URL."""
        api_key = os.environ.get("RCA_API_KEY", "")
        model = os.environ.get("RCA_MODEL", "")
        base_url = os.environ.get("RCA_API_BASE_URL", "https://api.openai.com/v1")
        if not api_key:
            raise ValueError("RCA_API_KEY is required to enable model-assisted investigation")
        if not model:
            raise ValueError("RCA_MODEL is required to enable model-assisted investigation")
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1_000,
    ) -> str:
        """Call chat completions and validate the response shape."""
        if not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")

        body = {
            "model": self._model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw_response = response.read()
        except HTTPError as exc:
            raise ModelProviderError(
                f"Chat provider returned HTTP {exc.code}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ModelProviderError(
                f"Chat provider request failed ({type(exc).__name__})"
            ) from exc

        try:
            payload = json.loads(raw_response)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelProviderError("Chat provider returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ModelProviderError("Chat provider response must be a JSON object")

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ModelProviderError("Chat provider response is missing choices[0]")
        message = choices[0].get("message")
        if not isinstance(message, Mapping):
            raise ModelProviderError("Chat provider response is missing a message")
        content = message.get("content")
        if not isinstance(content, str):
            raise ModelProviderError("Chat provider message content must be a string")
        return content
