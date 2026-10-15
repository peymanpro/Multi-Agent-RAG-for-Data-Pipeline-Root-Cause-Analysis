"""Stable JSON-compatible serialization for multi-agent investigation results."""

from __future__ import annotations

from typing import Any

from pipeline_rca.agents.models import InvestigationResult


def result_to_dict(result: InvestigationResult) -> dict[str, Any]:
    """Convert an investigation result to a stable, machine-readable report."""
    return {
        "case_id": result.case_id,
        "status": result.status.value,
        "model_assisted": result.model_assisted,
        "budget_exhausted": result.budget_exhausted,
        "affected_nodes": list(result.affected_nodes),
        "diagnostics": [
            {
                "code": finding.code,
                "fault_class": finding.fault_class.value,
                "severity": finding.severity.value,
                "summary": finding.summary,
                "evidence_ids": list(finding.evidence_ids),
                "observed": finding.observed,
                "expected": finding.expected,
            }
            for finding in result.diagnostics
        ],
        "hypotheses": [
            {
                "rank": rank,
                "fault_class": hypothesis.fault_class.value,
                "summary": hypothesis.summary,
                "confidence": round(hypothesis.confidence, 4),
                "confidence_is_calibrated": False,
                "status": hypothesis.status.value,
                "supporting_evidence_ids": list(hypothesis.supporting_evidence_ids),
                "contradicting_evidence_ids": list(
                    hypothesis.contradicting_evidence_ids
                ),
                "context_evidence_ids": list(hypothesis.context_evidence_ids),
                "finding_codes": list(hypothesis.finding_codes),
                "affected_nodes": list(hypothesis.affected_nodes),
                "rationale": hypothesis.rationale,
            }
            for rank, hypothesis in enumerate(result.hypotheses, start=1)
        ],
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "source": item.source,
                "locator": item.locator,
                "summary": item.summary[:800],
                "kind": item.kind,
                "observed_at": item.observed_at,
            }
            for item in result.evidence
        ],
        "verification_issues": [
            {
                "code": issue.code,
                "severity": issue.severity.value,
                "summary": issue.summary,
                "evidence_ids": list(issue.evidence_ids),
            }
            for issue in result.verification_issues
        ],
        "trace": [
            {
                "sequence": event.sequence,
                "agent": event.agent,
                "action": event.action,
                "status": event.status,
                "detail": event.detail,
                "input_refs": list(event.input_refs),
                "output_refs": list(event.output_refs),
                "elapsed_ms": event.elapsed_ms,
            }
            for event in result.trace
        ],
    }
