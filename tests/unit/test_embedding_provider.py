import json
from io import BytesIO
from unittest.mock import patch

import pytest

from pipeline_rca.retrieval.embeddings import (
    EmbeddingProviderError,
    OpenAICompatibleEmbeddingProvider,
)


def test_embeddings_adapter_restores_order_using_response_indices() -> None:
    response = {
        "data": [
            {"index": 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ]
    }
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="test-key",
        model="test-embedding-model",
        base_url="https://embeddings.example/v1",
    )

    with patch(
        "pipeline_rca.retrieval.embeddings.urlopen",
        return_value=BytesIO(json.dumps(response).encode("utf-8")),
    ) as mocked:
        vectors = provider.embed_texts(("first text", "second text"))

    assert vectors == ((1.0, 0.0), (0.0, 1.0))
    request = mocked.call_args.args[0]
    assert request.full_url == "https://embeddings.example/v1/embeddings"
    assert request.get_header("Authorization") == "Bearer test-key"
    assert json.loads(request.data)["input"] == ["first text", "second text"]


@pytest.mark.parametrize(
    "rows",
    [
        [{"index": 0, "embedding": [1.0, 0.0]}],
        [
            {"index": 0, "embedding": [1.0, 0.0]},
            {"index": 0, "embedding": [0.0, 1.0]},
        ],
        [
            {"index": 0, "embedding": [1.0, 0.0]},
            {"index": 1, "embedding": [0.0]},
        ],
        [
            {"index": 0, "embedding": [float("nan"), 0.0]},
            {"index": 1, "embedding": [0.0, 1.0]},
        ],
    ],
)
def test_embedding_adapter_rejects_malformed_vectors(rows: list[dict[str, object]]) -> None:
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="test-key",
        model="test-embedding-model",
    )
    body = json.dumps({"data": rows}).encode("utf-8")

    with patch(
        "pipeline_rca.retrieval.embeddings.urlopen",
        return_value=BytesIO(body),
    ):
        with pytest.raises(EmbeddingProviderError):
            provider.embed_texts(("first", "second"))


def test_embedding_adapter_enforces_batch_limits_and_configuration() -> None:
    with pytest.raises(ValueError, match="max_batch_size"):
        OpenAICompatibleEmbeddingProvider(
            api_key="key", model="embedding-model", max_batch_size=1.5  # type: ignore[arg-type]
        )
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="key", model="embedding-model", max_batch_size=1
    )
    with pytest.raises(ValueError, match="maximum"):
        provider.embed_texts(("one", "two"))
