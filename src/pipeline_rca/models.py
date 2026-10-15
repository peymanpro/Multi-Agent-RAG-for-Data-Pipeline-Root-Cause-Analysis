"""Typed domain contracts shared by diagnostics, retrieval, and agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping


class Severity(StrEnum):
    """Severity of an observed diagnostic finding."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FaultClass(StrEnum):
    """Normalized root-cause classes used by reports and benchmark evaluation."""

    SCHEMA_DRIFT = "schema_drift"
    DUPLICATE_RECORDS = "duplicate_records"
    STALE_INPUT = "stale_input"
    ROW_COUNT_MISMATCH = "row_count_mismatch"
    TASK_FAILURE = "task_failure"
    TRANSFORMATION_DEFECT = "transformation_defect"
    BROKEN_DEPENDENCY = "broken_dependency"
    UNKNOWN = "unknown"


class TaskStatus(StrEnum):
    """Normalized task/run outcome values."""

    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """A source-addressable observation available to an investigation."""

    evidence_id: str
    source: str
    locator: str
    summary: str
    kind: str
    observed_at: str | None = None


@dataclass(frozen=True, slots=True)
class SchemaSnapshot:
    """Observed schema for a named dataset."""

    dataset: str
    columns: tuple[str, ...]
    required_columns: tuple[str, ...] = ()
    schema_version: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetObservation:
    """A point-in-time observation of basic dataset health."""

    dataset: str
    row_count: int | None = None
    expected_row_count: int | None = None
    duplicate_key_count: int = 0
    latest_event_time: str | None = None
    freshness_threshold_seconds: int | None = None
    null_count_by_column: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TaskObservation:
    """A pipeline task or job execution observation."""

    task_id: str
    status: TaskStatus
    run_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class LineageEdge:
    """Directed dependency edge: upstream produces data consumed by downstream."""

    upstream: str
    downstream: str


@dataclass(frozen=True, slots=True)
class IncidentCase:
    """Observable input for an investigation.

    This model deliberately has no benchmark ground-truth field. Evaluator-only labels
    belong in a separate benchmark contract and must never be passed to investigators.
    """

    case_id: str
    question: str
    datasets: tuple[DatasetObservation, ...] = ()
    schemas: tuple[SchemaSnapshot, ...] = ()
    tasks: tuple[TaskObservation, ...] = ()
    lineage: tuple[LineageEdge, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class DiagnosticFinding:
    """A deterministic finding supported by one or more evidence identifiers."""

    code: str
    fault_class: FaultClass
    severity: Severity
    summary: str
    evidence_ids: tuple[str, ...] = ()
    observed: str | None = None
    expected: str | None = None


@dataclass(frozen=True, slots=True)
class InvestigationReport:
    """Result of deterministic analysis before any model-based interpretation."""

    case_id: str
    findings: tuple[DiagnosticFinding, ...]
    affected_nodes: tuple[str, ...] = ()
    status: str = "completed"

    @property
    def has_findings(self) -> bool:
        """Whether any deterministic diagnostic emitted a finding."""
        return bool(self.findings)
