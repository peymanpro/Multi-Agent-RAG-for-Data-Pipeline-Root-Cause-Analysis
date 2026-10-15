"""Persistent, content-addressed SQLite cache for text embeddings."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from pipeline_rca.retrieval.embeddings import EmbeddingProvider, EmbeddingProviderError

_SCHEMA_VERSION = "embedding-cache-v1"


class EmbeddingCacheError(RuntimeError):
    """A persistent embedding-cache operation failed safely."""


class CachedEmbeddingProvider:
    """Cache embeddings without storing the original input text.

    Cache keys are SHA-256 hashes of the provider namespace and exact input text.
    The namespace must change whenever model configuration can change embedding values.
    Existing SQLite rows contain only hashed keys and vectors, never raw prompts/runbooks.
    """

    def __init__(
        self,
        provider: EmbeddingProvider,
        *,
        cache_path: str | Path,
        namespace: str,
        max_batch_size: int = 64,
    ) -> None:
        if not namespace.strip():
            raise ValueError("namespace must be non-empty")
        if (
            isinstance(max_batch_size, bool)
            or not isinstance(max_batch_size, int)
            or max_batch_size < 1
        ):
            raise ValueError("max_batch_size must be a positive integer")
        self._provider = provider
        self.cache_path = Path(cache_path).expanduser()
        self._namespace_digest = hashlib.sha256(namespace.encode("utf-8")).hexdigest()
        self._max_batch_size = max_batch_size

    def _key_for(self, text: str) -> str:
        material = f"{_SCHEMA_VERSION}\0{self._namespace_digest}\0{text}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_vector(value: object) -> tuple[float, ...] | None:
        """Return a valid cached vector, or None for an invalid/stale row."""
        try:
            decoded = json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError:
            return None
        if not isinstance(decoded, list) or not decoded:
            return None

        vector: list[float] = []
        for item in decoded:
            if isinstance(item, bool) or not isinstance(item, int | float):
                return None
            number = float(item)
            if not math.isfinite(number):
                return None
            vector.append(number)
        if not math.isfinite(sum(component * component for component in vector)):
            return None
        if sum(component * component for component in vector) == 0.0:
            return None
        return tuple(vector)

    def _read_cached(self, keys: Sequence[str]) -> dict[str, tuple[float, ...]]:
        if not keys:
            return {}
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        placeholders = ",".join("?" for _ in keys)
        try:
            with sqlite3.connect(self.cache_path, timeout=30.0) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS embedding_cache (
                        cache_key TEXT PRIMARY KEY,
                        vector_json TEXT NOT NULL,
                        dimensions INTEGER NOT NULL CHECK (dimensions > 0)
                    )
                    """
                )
                rows = connection.execute(
                    f"SELECT cache_key, vector_json, dimensions FROM embedding_cache "
                    f"WHERE cache_key IN ({placeholders})",
                    tuple(keys),
                ).fetchall()
        except sqlite3.Error as exc:
            raise EmbeddingCacheError(
                f"embedding cache read failed ({type(exc).__name__})"
            ) from exc

        result: dict[str, tuple[float, ...]] = {}
        for key, raw_vector, dimensions in rows:
            vector = self._validate_vector(raw_vector)
            if vector is not None and len(vector) == dimensions:
                result[key] = vector
        return result

    def _write_cached(self, vectors: dict[str, tuple[float, ...]]) -> None:
        if not vectors:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            (key, json.dumps(vector, separators=(",", ":")), len(vector))
            for key, vector in sorted(vectors.items())
        ]
        try:
            with sqlite3.connect(self.cache_path, timeout=30.0) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS embedding_cache (
                        cache_key TEXT PRIMARY KEY,
                        vector_json TEXT NOT NULL,
                        dimensions INTEGER NOT NULL CHECK (dimensions > 0)
                    )
                    """
                )
                connection.executemany(
                    """
                    INSERT INTO embedding_cache(cache_key, vector_json, dimensions)
                    VALUES (?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        vector_json = excluded.vector_json,
                        dimensions = excluded.dimensions
                    """,
                    rows,
                )
        except sqlite3.Error as exc:
            raise EmbeddingCacheError(
                f"embedding cache write failed ({type(exc).__name__})"
            ) from exc

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Return cached vectors and embed only unique missing inputs in bounded batches."""
        items = tuple(texts)
        if not items:
            return ()
        if any(not isinstance(text, str) or not text.strip() for text in items):
            raise ValueError("embedding inputs must be non-empty strings")

        keys_by_text = {text: self._key_for(text) for text in dict.fromkeys(items)}
        cached = self._read_cached(tuple(keys_by_text.values()))
        missing_texts = [
            text for text, key in keys_by_text.items() if key not in cached
        ]

        newly_embedded: dict[str, tuple[float, ...]] = {}
        for start in range(0, len(missing_texts), self._max_batch_size):
            batch = missing_texts[start : start + self._max_batch_size]
            vectors = self._provider.embed_texts(batch)
            if len(vectors) != len(batch):
                raise EmbeddingProviderError(
                    "Embedding provider must return one vector per input"
                )
            for text, raw_vector in zip(batch, vectors, strict=True):
                vector = self._validate_vector(list(raw_vector))
                if vector is None:
                    raise EmbeddingProviderError(
                        "Embedding provider returned an invalid vector"
                    )
                newly_embedded[keys_by_text[text]] = vector

        self._write_cached(newly_embedded)
        all_vectors = cached | newly_embedded
        return tuple(all_vectors[keys_by_text[text]] for text in items)
