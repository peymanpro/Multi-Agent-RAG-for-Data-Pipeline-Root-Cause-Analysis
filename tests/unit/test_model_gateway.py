import json
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import patch

import pytest

from pipeline_rca.agents.model_gateway import (
    ModelProviderError,
    OpenAICompatibleChatModel,
)


def test_chat_adapter_sends_expected_contract_and_reads_content() -> None:
    response_body = json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": "structured answer"}}]}
    ).encode("utf-8")
    model = OpenAICompatibleChatModel(
        api_key="test-secret",
        model="test-model",
        base_url="https://model.example/v1/",
        timeout_seconds=7.0,
    )

    with patch(
        "pipeline_rca.agents.model_gateway.urlopen",
        return_value=BytesIO(response_body),
    ) as mocked:
        answer = model.complete(
            system_prompt="You are careful.",
            user_prompt="Analyze only the supplied evidence.",
            temperature=0.0,
            max_tokens=123,
        )

    assert answer == "structured answer"
    request = mocked.call_args.args[0]
    assert request.full_url == "https://model.example/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer test-secret"
    body = json.loads(request.data)
    assert body["model"] == "test-model"
    assert body["max_tokens"] == 123
    assert [item["role"] for item in body["messages"]] == ["system", "user"]
    assert mocked.call_args.kwargs["timeout"] == 7.0


def test_http_error_does_not_expose_api_key_or_provider_body() -> None:
    model = OpenAICompatibleChatModel(
        api_key="sensitive-test-key",
        model="test-model",
        base_url="https://model.example/v1",
    )
    error = HTTPError(
        "https://model.example/v1/chat/completions",
        401,
        "Unauthorized",
        hdrs=None,
        fp=BytesIO(b"provider response may contain sensitive details"),
    )

    with patch("pipeline_rca.agents.model_gateway.urlopen", side_effect=error):
        with pytest.raises(ModelProviderError) as captured:
            model.complete(system_prompt="system", user_prompt="user")

    assert "HTTP 401" in str(captured.value)
    assert "sensitive-test-key" not in str(captured.value)
    assert "provider response" not in str(captured.value)


def test_configuration_rejects_blank_key_and_insecure_scheme() -> None:
    with pytest.raises(ValueError, match="api_key"):
        OpenAICompatibleChatModel(api_key=" ", model="test-model")
    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        OpenAICompatibleChatModel(
            api_key="key",
            model="test-model",
            base_url="file:///tmp/model",
        )
