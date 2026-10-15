"""Unit tests for per-user bearer identities and scope grants."""

from __future__ import annotations

import json

import pytest

from pipeline_rca.api.auth import (
    AuthenticationConfigurationError,
    authenticate_bearer,
    configured_credentials,
    load_user_credentials,
)


TOKEN_A = "user-a-token-" + ("a" * 32)
TOKEN_B = "user-b-token-" + ("b" * 32)


def test_user_tokens_map_to_distinct_subjects_and_scopes() -> None:
    raw = json.dumps(
        [
            {
                "subject": "data-operator-a",
                "token": TOKEN_A,
                "scopes": ["investigations:run", "connectors:read"],
            },
            {
                "subject": "auditor-b",
                "token": TOKEN_B,
                "scopes": ["telemetry:read"],
            },
        ]
    )
    credentials = load_user_credentials(raw)

    operator = authenticate_bearer(f"Bearer {TOKEN_A}", credentials)
    auditor = authenticate_bearer(f"Bearer {TOKEN_B}", credentials)

    assert operator is not None
    assert operator.subject == "data-operator-a"
    assert operator.scopes == frozenset({"investigations:run", "connectors:read"})
    assert auditor is not None
    assert auditor.subject == "auditor-b"
    assert auditor.scopes == frozenset({"telemetry:read"})


def test_invalid_token_does_not_authenticate() -> None:
    credentials = load_user_credentials(
        json.dumps([{"subject": "operator", "token": TOKEN_A, "scopes": ["investigations:run"]}])
    )

    assert authenticate_bearer("Bearer wrong-token", credentials) is None
    assert authenticate_bearer(TOKEN_A, credentials) is None


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        "{}",
        "[]",
        json.dumps([{"subject": "operator", "token": "short", "scopes": ["investigations:run"]}]),
        json.dumps([{"subject": "operator", "token": TOKEN_A, "scopes": ["admin:*"]}]),
        json.dumps(
            [
                {"subject": "same", "token": TOKEN_A, "scopes": ["investigations:run"]},
                {"subject": "same", "token": TOKEN_B, "scopes": ["investigations:run"]},
            ]
        ),
    ],
)
def test_invalid_identity_configuration_is_rejected(raw: str) -> None:
    with pytest.raises(AuthenticationConfigurationError):
        load_user_credentials(raw)


def test_shared_token_and_user_registry_cannot_be_configured_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RCA_API_AUTH_TOKEN", TOKEN_A)
    with pytest.raises(AuthenticationConfigurationError, match="not both"):
        configured_credentials(users_json=json.dumps([
            {"subject": "operator", "token": TOKEN_B, "scopes": ["investigations:run"]}
        ]))
