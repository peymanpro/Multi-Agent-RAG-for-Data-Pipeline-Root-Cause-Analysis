"""Security-oriented tests for the bounded read-only connector transport."""

from __future__ import annotations

import pytest

from pipeline_rca.connectors.base import ConnectorError, HttpJsonClient, validate_base_url


def test_only_loopback_allows_plaintext_http() -> None:
    assert validate_base_url("http://127.0.0.1:8080/") == "http://127.0.0.1:8080"
    with pytest.raises(ConnectorError, match="loopback"):
        validate_base_url("http://airflow.internal:8080")


@pytest.mark.parametrize(
    "url",
    [
        "relative/path",
        "ftp://example.com",
        "https://user:pass@example.com",
        "https://example.com?token=secret",
        "https://example.com/#fragment",
    ],
)
def test_connector_base_url_rejects_unsafe_forms(url: str) -> None:
    with pytest.raises(ConnectorError):
        validate_base_url(url)


def test_http_client_rejects_paths_that_can_change_origin_or_traverse() -> None:
    client = HttpJsonClient("https://example.com")
    with pytest.raises(ConnectorError, match="relative API path"):
        client.get_json("//attacker.example/data")
    with pytest.raises(ConnectorError, match="traverse"):
        client.get_json("../admin")
