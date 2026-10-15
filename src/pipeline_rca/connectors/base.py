"""Shared bounded HTTP transport and safe URL handling for read-only connectors."""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit

from pipeline_rca.models import EvidenceRecord


class ConnectorError(RuntimeError):
    """A configured source could not be read or normalized safely."""


class JsonGetClient(Protocol):
    """Minimal transport contract consumed by REST-based connectors."""

    def get_json(self, path: str) -> dict[str, Any]:
        """GET a bounded JSON response from a preconfigured origin."""
        ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        """Refuse redirects so credentials are never forwarded to a new origin."""
        return None


def validate_base_url(base_url: str) -> str:
    """Require an absolute HTTP(S) origin; allow plaintext HTTP only on loopback."""
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ConnectorError("connector base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConnectorError("connector base URL must not contain credentials, query, or fragment")
    if parsed.scheme == "http":
        host = parsed.hostname.lower()
        if host != "localhost" and host != "127.0.0.1" and host != "::1":
            raise ConnectorError("plaintext HTTP is permitted only for loopback development")
    return base_url.rstrip("/")


def evidence_identifier(source: str, locator: str, payload: object) -> str:
    """Create a stable opaque evidence identifier without embedding source secrets."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(f"{source}\0{locator}\0{encoded}".encode()).hexdigest()[:20]
    return f"{source}:{digest}"


def make_evidence(
    *,
    source: str,
    locator: str,
    summary: str,
    kind: str,
    payload_for_id: object,
    observed_at: str | None = None,
) -> EvidenceRecord:
    """Create bounded metadata evidence; raw payloads are never copied into summaries."""
    return EvidenceRecord(
        evidence_id=evidence_identifier(source, locator, payload_for_id),
        source=source,
        locator=locator[:300],
        summary=summary[:700],
        kind=kind,
        observed_at=observed_at,
    )


class HttpJsonClient:
    """Small synchronous GET-only JSON transport with auth and response-size limits."""

    def __init__(
        self,
        base_url: str,
        *,
        bearer_token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout_seconds: float = 8.0,
        max_response_bytes: int = 4_000_000,
    ) -> None:
        self.base_url = validate_base_url(base_url)
        if bearer_token and (username or password):
            raise ConnectorError("configure either Bearer auth or Basic auth, not both")
        if (username is None) != (password is None):
            raise ConnectorError("Basic auth requires both username and password")
        if timeout_seconds <= 0 or max_response_bytes < 1:
            raise ConnectorError("connector timeout and response limit must be positive")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._headers = {"Accept": "application/json"}
        if bearer_token:
            self._headers["Authorization"] = f"Bearer {bearer_token}"
        elif username is not None and password is not None:
            encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
            self._headers["Authorization"] = f"Basic {encoded}"
        self._opener = urllib.request.build_opener(_NoRedirect)

    def get_json(self, path: str) -> dict[str, Any]:
        """Issue an allowlisted relative GET, reject redirects, and cap the response bytes."""
        if not isinstance(path, str) or not path or path.startswith("//"):
            raise ConnectorError("connector path must be a relative API path")
        parsed_path = urllib.parse.urlsplit(path)
        if parsed_path.scheme or parsed_path.netloc or any(
            segment == ".." for segment in parsed_path.path.split("/")
        ):
            raise ConnectorError("connector path must not change origin or traverse directories")
        url = f"{self.base_url}/{path.lstrip('/')}"
        request = urllib.request.Request(url, headers=self._headers, method="GET")
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                final = urlsplit(response.geturl())
                origin = urlsplit(self.base_url)
                if (final.scheme, final.netloc) != (origin.scheme, origin.netloc):
                    raise ConnectorError("connector response origin changed unexpectedly")
                body = response.read(self.max_response_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise ConnectorError(f"read-only connector returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectorError(
                f"read-only connector request failed ({type(exc).__name__})"
            ) from exc
        if len(body) > self.max_response_bytes:
            raise ConnectorError("connector response exceeded the configured byte limit")
        try:
            decoded: Any = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ConnectorError("connector response was not valid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise ConnectorError("connector JSON response must be an object")
        return dict(decoded)
