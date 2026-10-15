"""FastAPI application exposing bounded, read-only incident investigation."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, field_validator

from pipeline_rca import __version__
from pipeline_rca.agents.orchestrator import InvestigationOrchestrator
from pipeline_rca.agents.reporting import result_to_dict
from pipeline_rca.retrieval.corpus import MarkdownCorpus
from pipeline_rca.serialization import incident_case_from_mapping

_MAX_CASE_CHARACTERS = 256_000


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


def create_app(*, runbooks_dir: str | Path | None = None) -> FastAPI:
    """Create an API instance with a locally loaded corpus and no model provider."""
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
    application.state.runbook_corpus = corpus
    application.state.runbook_error = corpus_error

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
                detail="runbook retrieval is unavailable; set use_runbooks=false for diagnostics only",
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
