"""Typed contracts for bounded multi-agent investigation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pipeline_rca.models import DiagnosticFinding, EvidenceRecord, FaultClass, Severity


class HypothesisStatus(StrEnum):
    """Epistemic status of a proposed root cause."""

    SUPPORTED = "supported"
    LOW_EVIDENCE = "low_evidence"
    UNVERIFIED = "unverified"


class InvestigationStatus(StrEnum):
    """Overall completeness of an investigation."""

    COMPLETED = "completed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    PARTIAL = "partial"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True, slots=True)
class AgentBudget:
    """Explicit, validated limits for a single investigation."""

    max_agent_steps: int = 8
    max_retrieval_hits: int = 5
    max_evidence_records: int = 60
    max_hypotheses: int = 5
    max_prompt_chars: int = 12_000
    model_timeout_seconds: float = 20.0
    model_max_output_tokens: int = 1_000

    def __post_init__(self) -> None:
        positive_ints = {
            "max_agent_steps": self.max_agent_steps,
            "max_retrieval_hits": self.max_retrieval_hits,
            "max_evidence_records": self.max_evidence_records,
            "max_hypotheses": self.max_hypotheses,
            "max_prompt_chars": self.max_prompt_chars,
            "model_max_output_tokens": self.model_max_output_tokens,
        }
        for name, value in positive_ints.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.model_timeout_seconds <= 0:
            raise ValueError("model_timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class AgentTraceEvent:
    """One auditable agent step with stable references, not copied secrets."""

    sequence: int
    agent: str
    action: str
    status: str
    detail: str
    input_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()
    elapsed_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class RootCauseHypothesis:
    """A ranked suspected cause with explicit evidence references."""

    fault_class: FaultClass
    summary: str
    confidence: float
    status: HypothesisStatus
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    context_evidence_ids: tuple[str, ...] = ()
    finding_codes: tuple[str, ...] = ()
    affected_nodes: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class VerificationIssue:
    """A verification warning attached to a report or hypothesis."""

    code: str
    severity: Severity
    summary: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InvestigationResult:
    """Full multi-agent result with diagnostics, citations, and execution trace."""

    case_id: str
    status: InvestigationStatus
    diagnostics: tuple[DiagnosticFinding, ...]
    hypotheses: tuple[RootCauseHypothesis, ...]
    evidence: tuple[EvidenceRecord, ...]
    verification_issues: tuple[VerificationIssue, ...]
    affected_nodes: tuple[str, ...]
    trace: tuple[AgentTraceEvent, ...]
    model_assisted: bool = False
    budget_exhausted: bool = False

    @property
    def has_hypotheses(self) -> bool:
        """Whether at least one cause hypothesis was proposed."""
        return bool(self.hypotheses)
