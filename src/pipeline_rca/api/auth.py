"""Per-user API token authentication and scope-based authorization."""

from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass
from typing import Any

ALLOWED_SCOPES = frozenset({"investigations:run", "connectors:read", "telemetry:read"})


class AuthenticationConfigurationError(ValueError):
    """The API identity configuration is missing, ambiguous, or unsafe."""


@dataclass(frozen=True, slots=True)
class ApiPrincipal:
    """An authenticated subject with explicitly granted API scopes."""

    subject: str
    scopes: frozenset[str]


@dataclass(frozen=True, slots=True)
class TokenCredential:
    """A server-side bearer token associated with a subject and scopes."""

    token: str
    principal: ApiPrincipal


def load_user_credentials(raw: str | None) -> tuple[TokenCredential, ...]:
    """Parse a JSON array of users without ever logging token values.

    Each entry has subject, token, and scopes fields. The configuration must come from a
    secret manager or a protected runtime environment, never from a committed file.
    """
    if not raw:
        return ()
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AuthenticationConfigurationError("RCA_API_USERS_JSON is invalid JSON") from exc
    if not isinstance(parsed, list) or not parsed:
        raise AuthenticationConfigurationError("RCA_API_USERS_JSON must be a non-empty array")

    credentials: list[TokenCredential] = []
    subjects: set[str] = set()
    tokens: set[str] = set()
    for index, item in enumerate(parsed):
        if not isinstance(item, dict) or set(item) != {"subject", "token", "scopes"}:
            raise AuthenticationConfigurationError(
                f"RCA_API_USERS_JSON entry {index} must contain subject, token, and scopes"
            )
        subject, token, scopes = item["subject"], item["token"], item["scopes"]
        if not isinstance(subject, str) or not subject or len(subject) > 128:
            raise AuthenticationConfigurationError(f"entry {index} has an invalid subject")
        if subject.strip() != subject or subject in subjects:
            raise AuthenticationConfigurationError(
                f"entry {index} has a duplicate or invalid subject"
            )
        if not isinstance(token, str) or len(token) < 32 or token.strip() != token:
            raise AuthenticationConfigurationError(
                f"entry {index} token must be at least 32 characters without surrounding whitespace"
            )
        if token in tokens:
            raise AuthenticationConfigurationError("duplicate API tokens are not allowed")
        if (
            not isinstance(scopes, list)
            or not scopes
            or any(not isinstance(scope, str) for scope in scopes)
            or len(scopes) != len(set(scopes))
            or not set(scopes) <= ALLOWED_SCOPES
        ):
            raise AuthenticationConfigurationError(f"entry {index} has invalid scopes")

        subjects.add(subject)
        tokens.add(token)
        credentials.append(
            TokenCredential(token, ApiPrincipal(subject, frozenset(scopes)))
        )
    return tuple(credentials)


def configured_credentials(
    *, legacy_token: str | None = None, users_json: str | None = None
) -> tuple[TokenCredential, ...]:
    """Load per-user credentials, preserving the older shared-token setting for migration."""
    configured_users = (
        users_json if users_json is not None else os.environ.get("RCA_API_USERS_JSON")
    )
    credentials = load_user_credentials(configured_users)
    if credentials:
        if legacy_token or os.environ.get("RCA_API_AUTH_TOKEN"):
            raise AuthenticationConfigurationError(
                "configure RCA_API_USERS_JSON or RCA_API_AUTH_TOKEN, not both"
            )
        return credentials

    token = legacy_token if legacy_token is not None else os.environ.get("RCA_API_AUTH_TOKEN")
    if token == "":
        token = None
    if token is None:
        return ()
    if token.strip() != token or len(token) < 32:
        raise AuthenticationConfigurationError(
            "RCA_API_AUTH_TOKEN must be at least 32 characters without surrounding whitespace"
        )
    return (
        TokenCredential(
            token,
            ApiPrincipal("shared-token", frozenset({"investigations:run"})),
        ),
    )


def authenticate_bearer(
    authorization: str, credentials: tuple[TokenCredential, ...]
) -> ApiPrincipal | None:
    """Constant-time compare against configured tokens and return the matching principal."""
    supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
    matched: ApiPrincipal | None = None
    # Evaluate every candidate instead of stopping at the first match.
    for credential in credentials:
        is_match = hmac.compare_digest(
            supplied.encode("utf-8"), credential.token.encode("utf-8")
        )
        if is_match:
            matched = credential.principal
    return matched
