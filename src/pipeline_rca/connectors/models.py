"""Normalized, source-addressable snapshots emitted by data connectors."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline_rca.models import (
    DatasetObservation,
    EvidenceRecord,
    IncidentCase,
    LineageEdge,
    SchemaSnapshot,
    TaskObservation,
)


@dataclass(frozen=True, slots=True)
class ConnectorSnapshot:
    """Read-only connector output normalized into the investigation domain contracts."""

    source: str
    observed_at: str
    evidence: tuple[EvidenceRecord, ...]
    tasks: tuple[TaskObservation, ...] = ()
    lineage: tuple[LineageEdge, ...] = ()
    schemas: tuple[SchemaSnapshot, ...] = ()
    datasets: tuple[DatasetObservation, ...] = ()

    def to_incident_case(self, *, case_id: str, question: str) -> IncidentCase:
        """Create an observable incident case without inventing evaluator truth."""
        return IncidentCase(
            case_id=case_id,
            question=question,
            datasets=self.datasets,
            schemas=self.schemas,
            tasks=self.tasks,
            lineage=self.lineage,
            evidence=self.evidence,
        )
