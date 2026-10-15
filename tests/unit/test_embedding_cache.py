"""Tests for persistent, content-addressed embedding caching."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from collections.abc import Sequence

import pytest

from pipeline_rca.retrieval.embedding_cache import (
    CachedEmbeddingProvider,
    EmbeddingCacheError,
)
from pipeline_rca.retrieval.embeddings import EmbeddingProviderError


class CountingProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        items = tuple(texts)
        self.calls.append(items)
        return tuple((float(len(text)), 1.0) for text in items)


def _cache(
    provider: CountingProvider,
    path: Path,
    *,
    namespace: str = "provider/model/version-1",
    max_batch_size: int = 64,
) -> CachedEmbeddingProvider:
    return CachedEmbeddingProvider(
        provider,
        cache_path=path,
        namespace=namespace,
        max_batch_size=max_batch_size,
    )


def test_cached_provider_reuses_vectors_across_instances_without_storing_text(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "cache" / "embeddings.sqlite3"
    first_provider = CountingProvider()
    first = _cache(first_provider, cache_path)
    texts = ("private runbook phrase", "duplicate record retry", "private runbook phrase")

    first_result = first.embed_texts(texts)

    assert first_result[0] == first_result[2]
    assert first_provider.calls == [("private runbook phrase", "duplicate record retry")]

    second_provider = CountingProvider()
    second = _cache(second_provider, cache_path)
    second_result = second.embed_texts(texts)

    assert second_result == first_result
    assert second_provider.calls == []
    assert cache_path.is_file()
    assert b"private runbook phrase" not in cache_path.read_bytes()
    assert b"duplicate record retry" not in cache_path.read_bytes()


def test_cache_namespace_partitions_model_or_provider_identity(tmp_path: Path) -> None:
    cache_path = tmp_path / "embeddings.sqlite3"
    first_provider = CountingProvider()
    _cache(first_provider, cache_path, namespace="model-A").embed_texts(("same text",))

    second_provider = CountingProvider()
    second_result = _cache(
        second_provider, cache_path, namespace="model-B"
    ).embed_texts(("same text",))

    assert second_provider.calls == [("same text",)]
    assert second_result == ((9.0, 1.0),)


def test_cache_batches_unique_missing_texts_within_provider_limit(tmp_path: Path) -> None:
    provider = CountingProvider()
    cached = _cache(provider, tmp_path / "embeddings.sqlite3", max_batch_size=2)

    result = cached.embed_texts(("alpha", "beta", "gamma", "delta", "epsilon"))

    assert len(result) == 5
    assert [len(batch) for batch in provider.calls] == [2, 2, 1]


def test_corrupt_cache_row_is_recomputed_and_repaired(tmp_path: Path) -> None:
    cache_path = tmp_path / "embeddings.sqlite3"
    provider = CountingProvider()
    cached = _cache(provider, cache_path)
    cache_key = cached._key_for("schema drift")

    with sqlite3.connect(cache_path) as connection:
        connection.execute(
            """
            CREATE TABLE embedding_cache (
                cache_key TEXT PRIMARY KEY,
                vector_json TEXT NOT NULL,
                dimensions INTEGER NOT NULL CHECK (dimensions > 0)
            )
            """
        )
        connection.execute(
            "INSERT INTO embedding_cache(cache_key, vector_json, dimensions) "
            "VALUES (?, ?, ?)",
            (cache_key, "not-json", 2),
        )

    result = cached.embed_texts(("schema drift",))

    assert result == ((12.0, 1.0),)
    assert provider.calls == [("schema drift",)]
    with sqlite3.connect(cache_path) as connection:
        row = connection.execute(
            "SELECT vector_json, dimensions FROM embedding_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    assert row == ("[12.0,1.0]", 2)


def test_invalid_provider_vector_is_not_persisted(tmp_path: Path) -> None:
    class InvalidProvider:
        def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
            return ((0.0, 0.0),)

    cache_path = tmp_path / "embeddings.sqlite3"
    cached = CachedEmbeddingProvider(
        InvalidProvider(),
        cache_path=cache_path,
        namespace="test",
    )

    with pytest.raises(EmbeddingProviderError, match="invalid vector"):
        cached.embed_texts(("a valid input",))

    assert not cache_path.exists()


def test_cache_storage_failure_returns_safe_error(tmp_path: Path) -> None:
    cache_path = tmp_path / "not-a-database"
    cache_path.mkdir()
    cached = _cache(CountingProvider(), cache_path)

    with pytest.raises(EmbeddingCacheError, match="embedding cache read failed"):
        cached.embed_texts(("cache storage unavailable",))


def test_cache_rejects_invalid_configuration(tmp_path: Path) -> None:
    provider = CountingProvider()
    with pytest.raises(ValueError, match="namespace"):
        CachedEmbeddingProvider(provider, cache_path=tmp_path / "cache.sqlite3", namespace=" ")
    with pytest.raises(ValueError, match="max_batch_size"):
        CachedEmbeddingProvider(
            provider,
            cache_path=tmp_path / "cache.sqlite3",
            namespace="test",
            max_batch_size=0,
        )
