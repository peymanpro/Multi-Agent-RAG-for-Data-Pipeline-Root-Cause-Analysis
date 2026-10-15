"""Provider-neutral text embedding interface and OpenAI-compatible HTTP adapter."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping, Sequence
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class EmbeddingProviderError(RuntimeError):
    """Safe embedding-provider invocation failure."""


class EmbeddingProvider(Protocol):
    """Interface for batch embedding providers."""

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Return one finite, non-zero vector per input string in input order."""


class OpenAICompatibleEmbeddingProvider:
    """Adapter for APIs implementing the OpenAI embeddings request/response shape.

    Credentials are read at runtime and error messages never include the API key or
    provider response body. This adapter is opt-in; the default BM25 pipeline is offline.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
        max_batch_size: int = 64,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must be non-empty")
        if not model.strip():
            raise ValueError("model must be non-empty")
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("base_url must use HTTP or HTTPS")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if isinstance(max_batch_size, bool) or max_batch_size < 1:
            raise ValueError("max_batch_size must be a positive integer")

        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_batch_size = max_batch_size

    @classmethod
    def from_env(
        cls,
        *,
        timeout_seconds: float = 20.0,
        max_batch_size: int = 64,
    ) -> OpenAICompatibleEmbeddingProvider:
        """Configure through RCA_API_KEY, RCA_EMBEDDING_MODEL, and optional RCA_API_BASE_URL."""
        api_key = os.environ.get("RCA_API_KEY", "")
        model = os.environ.get("RCA_EMBEDDING_MODEL", "")
        base_url = os.environ.get("RCA_API_BASE_URL", "https://api.openai.com/v1")
        if not api_key:
            raise ValueError("RCA_API_KEY is required for hybrid retrieval")
        if not model:
            raise ValueError("RCA_EMBEDDING_MODEL is required for hybrid retrieval")
        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_batch_size=max_batch_size,
        )

    def embed_texts(
        self, texts: Sequence[str]
    ) -> tuple[tuple[float, ...], ...]:
        """Embed a bounded batch and validate its dimension/order contract."""
        items = tuple(texts)
        if not items:
            return ()
        if len(items) > self._max_batch_size:
            raise ValueError(
                f"batch has {len(items)} texts; maximum is {self._max_batch_size}"
            )
        if any(not isinstance(text, str) or not text.strip() for text in items):
            raise ValueError("embedding inputs must be non-empty strings")

        request = Request(
            f"{self._base_url}/embeddings",
            data=json.dumps({"model": self._model, "input": list(items)}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw_response = response.read(4_000_001)
        except HTTPError as exc:
            raise EmbeddingProviderError(
                f"Embedding provider returned HTTP {exc.code}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise EmbeddingProviderError(
                f"Embedding provider request failed ({type(exc).__name__})"
            ) from exc

        if len(raw_response) > 4_000_000:
            raise EmbeddingProviderError("Embedding provider response exceeded 4 MB")
        try:
            payload = json.loads(raw_response)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EmbeddingProviderError("Embedding provider returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise EmbeddingProviderError("Embedding provider response must be a JSON object")

        rows = payload.get("data")
        if not isinstance(rows, list) or len(rows) != len(items):
            raise EmbeddingProviderError(
                "Embedding provider must return one vector per input"
            )

        ordered: list[tuple[float, ...] | None] = [None] * len(items)
        dimension: int | None = None
        for row in rows:
            if not isinstance(row, Mapping):
                raise EmbeddingProviderError("Embedding data entries must be objects")
            index = row.get("index")
            vector = row.get("embedding")
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(items):
                raise EmbeddingProviderError("Embedding response contains an invalid index")
            if ordered[index] is not None:
                raise EmbeddingProviderError("Embedding response contains duplicate indices")
            if not isinstance(vector, list) or not vector:
                raise EmbeddingProviderError("Embedding vector must be a non-empty array")

            parsed: list[float] = []
            for value in vector:
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise EmbeddingProviderError("Embedding vector values must be numeric")
                number = float(value)
                if not math.isfinite(number):
                    raise EmbeddingProviderError("Embedding vector values must be finite")
                parsed.append(number)

            if dimension is None:
                dimension = len(parsed)
            elif len(parsed) != dimension:
                raise EmbeddingProviderError("Embedding vectors have inconsistent dimensions")
            norm = math.sqrt(sum(value * value for value in parsed))
            if norm == 0:
                raise EmbeddingProviderError("Embedding vector cannot be all zeros")
            ordered[index] = tuple(parsed)

        if any(vector is None for vector in ordered):
            raise EmbeddingProviderError("Embedding response omitted an input index")
        return tuple(vector for vector in ordered if vector is not None)
