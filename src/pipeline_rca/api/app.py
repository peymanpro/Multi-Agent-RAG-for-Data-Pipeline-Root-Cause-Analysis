"""FastAPI application exposing bounded, read-only incident investigation."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, field_validator
from starlette.middleware.base import RequestResponseEndpoint

from pipeline_rca import __version__
from pipeline_rca.agents.orchestrator import InvestigationOrchestrator
from pipeline_rca.agents.reporting import result_to_dict
from pipeline_rca.api.auth import authenticate_bearer, configured_credentials
from pipeline_rca.api.rate_limit import (
    InMemoryRateLimitStore,
    RateLimitBackendError,
    RateLimitDecision,
    RateLimitStore,
    RedisRateLimitStore,
    build_rate_limit_store,
    positive_environment_int,
)
from pipeline_rca.api.request_limits import RequestBodyLimitMiddleware
from pipeline_rca.api.telemetry import RequestTelemetryMiddleware
from pipeline_rca.retrieval.corpus import MarkdownCorpus
from pipeline_rca.serialization import incident_case_from_mapping

_MAX_CASE_CHARACTERS = 256_000
_MAX_REQUEST_BODY_BYTES = 300_000


class InvestigationRequest(BaseModel):
    """Validated HTTP request; intentionally excludes model/provider controls."""

    model_config = ConfigDict(extra="forbid")

    case: dict[str, Any]
    as_of: datetime | None = None
    use_runbooks: bool = True

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        """Reject machine-local timestamps that would make freshness checks ambiguous."""
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("as_of must include an explicit UTC offset")
        return value


def _load_corpus(directory: Path) -> tuple[MarkdownCorpus | None, str | None]:
    """Load the read-only runbook corpus and return a safe diagnostic code on failure."""
    try:
        corpus = MarkdownCorpus.from_directory(directory)
    except (OSError, ValueError):
        return None, "runbook_corpus_unavailable"
    if not corpus.documents or not corpus.chunks:
        return None, "runbook_corpus_empty"
    return corpus, None


def _rate_limit_headers(decision: RateLimitDecision) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(decision.remaining),
        "Retry-After": str(decision.retry_after_seconds),
    }


def _rate_limited_response(decision: RateLimitDecision) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "request rate limit exceeded"},
        headers=_rate_limit_headers(decision),
    )


def create_app(
    *,
    runbooks_dir: str | Path | None = None,
    auth_token: str | None = None,
    users_json: str | None = None,
    rate_limit_store: RateLimitStore | None = None,
    rate_limit_requests: int | None = None,
    rate_limit_window_seconds: int | None = None,
) -> FastAPI:
    """Create a read-only API with optional per-user bearer identities and scopes."""
    credentials = configured_credentials(legacy_token=auth_token, users_json=users_json)
    production_mode = os.environ.get("RCA_DEPLOYMENT_MODE", "development").lower() == "production"
    auth_required = production_mode or os.environ.get("RCA_API_AUTH_REQUIRED", "").lower() in {
        "1", "true", "yes"
    }
    if auth_required and not credentials:
        raise ValueError("API authentication is required but no API users are configured")
    if rate_limit_store is None:
        rate_limit_store = build_rate_limit_store(
            redis_url=os.environ.get("RCA_RATE_LIMIT_REDIS_URL"),
            production_mode=production_mode,
        )
    elif production_mode and not rate_limit_store.is_distributed:
        raise ValueError("production mode requires a distributed Redis rate-limit store")
    effective_rate_limit = (
        rate_limit_requests
        if rate_limit_requests is not None
        else positive_environment_int("RCA_RATE_LIMIT_REQUESTS", 30)
    )
    effective_rate_window = (
        rate_limit_window_seconds
        if rate_limit_window_seconds is not None
        else positive_environment_int("RCA_RATE_LIMIT_WINDOW_SECONDS", 60)
    )
    if effective_rate_limit < 1 or effective_rate_window < 1:
        raise ValueError("rate-limit budget and window must be positive integers")
    configured_path = (
        Path(runbooks_dir)
        if runbooks_dir is not None
        else Path(os.environ.get("RCA_RUNBOOKS_DIR", "data/runbooks"))
    )
    corpus, corpus_error = _load_corpus(configured_path)

    application = FastAPI(
        title="Pipeline RCA API",
        summary="Evidence-grounded, read-only data-pipeline incident investigation.",
        description=(
            "Runs deterministic diagnostics, local runbook retrieval, bounded hypothesis "
            "synthesis, and evidence-reference verification. This API does not call a hosted "
            "model or modify production systems."
        ),
        version=__version__,
    )
    application.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=_MAX_REQUEST_BODY_BYTES,
    )
    application.add_middleware(RequestTelemetryMiddleware)
    application.state.runbook_corpus = corpus
    application.state.runbook_error = corpus_error
    application.state.rate_limit_store = rate_limit_store
    application.state.rate_limit_requests = effective_rate_limit
    application.state.rate_limit_window_seconds = effective_rate_window

    if isinstance(rate_limit_store, RedisRateLimitStore):
        async def close_rate_limit_store() -> None:
            await rate_limit_store.close()

        application.add_event_handler("shutdown", close_rate_limit_store)

    @application.middleware("http")
    async def authenticate_investigations(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Authenticate, authorize, and rate-limit investigation calls."""
        is_investigation = (
            request.method == "POST" and request.url.path == "/v1/investigations"
        )
        if not is_investigation:
            return await call_next(request)

        client_host = request.client.host if request.client is not None else "unknown"
        try:
            # IP budget also protects the endpoint from repeated invalid-token probes.
            ip_decision = await rate_limit_store.consume(
                f"ip:{client_host}",
                limit=effective_rate_limit,
                window_seconds=effective_rate_window,
            )
        except RateLimitBackendError:
            return JSONResponse(
                status_code=503,
                content={"detail": "rate-limit backend is unavailable"},
            )
        if not ip_decision.allowed:
            return _rate_limited_response(ip_decision)

        principal = None
        if credentials:
            principal = authenticate_bearer(
                request.headers.get("authorization", ""),
                credentials,
            )
            if principal is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "valid Bearer authentication is required"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
            request.state.principal = principal
            request.scope.setdefault("state", {})["principal_subject"] = principal.subject
            if "investigations:run" not in principal.scopes:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "the authenticated subject lacks investigations:run"},
                )
            try:
                subject_decision = await rate_limit_store.consume(
                    f"subject:{principal.subject}",
                    limit=effective_rate_limit,
                    window_seconds=effective_rate_window,
                )
            except RateLimitBackendError:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "rate-limit backend is unavailable"},
                )
            if not subject_decision.allowed:
                return _rate_limited_response(subject_decision)
        elif auth_required:
            return JSONResponse(
                status_code=503,
                content={"detail": "API identity configuration is unavailable"},
            )
        else:
            request.scope.setdefault("state", {})["principal_subject"] = "anonymous"

        response = await call_next(request)
        decision = (
            subject_decision if credentials else ip_decision
        ) if credentials else ip_decision
        response.headers.update(_rate_limit_headers(decision))
        return response

    @application.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        """Return process liveness without depending on retrieval availability."""
        return {"status": "ok"}

    @application.get("/health/ready", tags=["health"], response_model=None)
    def ready() -> dict[str, str | int | bool] | JSONResponse:
        """Report whether the configured read-only runbook corpus is available."""
        current_corpus: MarkdownCorpus | None = application.state.runbook_corpus
        if current_corpus is None:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "retrieval_available": False,
                    "reason": application.state.runbook_error or "runbook_corpus_unavailable",
                },
            )
        return {
            "status": "ready",
            "retrieval_available": True,
            "runbook_document_count": len(current_corpus.documents),
            "runbook_chunk_count": len(current_corpus.chunks),
            "rate_limit_backend": "redis" if rate_limit_store.is_distributed else "process-local",
        }

    @application.post("/v1/investigations", tags=["investigation"])
    def investigate(payload: InvestigationRequest) -> dict[str, Any]:
        """Run an offline, bounded investigation for a validated observable case."""
        encoded_case = json.dumps(payload.case, separators=(",", ":"), ensure_ascii=False)
        if len(encoded_case) > _MAX_CASE_CHARACTERS:
            raise HTTPException(
                status_code=413,
                detail=f"case payload exceeds {_MAX_CASE_CHARACTERS} characters",
            )

        current_corpus: MarkdownCorpus | None = application.state.runbook_corpus
        if payload.use_runbooks and current_corpus is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "runbook retrieval is unavailable; set use_runbooks=false "
                    "for diagnostics only"
                ),
            )

        try:
            case = incident_case_from_mapping(payload.case)
            result = InvestigationOrchestrator(
                corpus=current_corpus if payload.use_runbooks else None
            ).run(case, as_of=payload.as_of)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return result_to_dict(result)

    return application


app = create_app()
