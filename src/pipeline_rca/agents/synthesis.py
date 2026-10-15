"""Evidence-aware, deterministic hypothesis synthesis."""

from __future__ import annotations

from collections import defaultdict

from pipeline_rca.agents.models import (
    HypothesisStatus,
    RootCauseHypothesis,
)
from pipeline_rca.agents.specialists import find_context_runbooks
from pipeline_rca.models import (
    DiagnosticFinding,
    EvidenceRecord,
    FaultClass,
    IncidentCase,
    Severity,
)
from pipeline_rca.retrieval.models import RetrievalHit


_BASE_CONFIDENCE = {
    Severity.CRITICAL: 0.76,
    Severity.ERROR: 0.65,
    Severity.WARNING: 0.48,
    Severity.INFO: 0.35,
}


class DeterministicHypothesisAgent:
    """Create ranked hypotheses from deterministic findings without an LLM."""

    name = "hypothesis-synthesis-agent"

    def run(
        self,
        case: IncidentCase,
        findings: tuple[DiagnosticFinding, ...],
        evidence: tuple[EvidenceRecord, ...],
        hits: tuple[RetrievalHit, ...],
        affected_nodes: tuple[str, ...],
        *,
        max_hypotheses: int = 5,
    ) -> tuple[RootCauseHypothesis, ...]:
        """Group findings by fault class and attach only resolvable evidence IDs."""
        if max_hypotheses < 1:
            raise ValueError("max_hypotheses must be positive")

        allowed_evidence_ids = {item.evidence_id for item in evidence}
        by_class: dict[FaultClass, list[DiagnosticFinding]] = defaultdict(list)
        for finding in findings:
            if finding.fault_class != FaultClass.UNKNOWN:
                by_class[finding.fault_class].append(finding)

        hypotheses: list[RootCauseHypothesis] = []
        for fault_class, class_findings in by_class.items():
            class_findings.sort(
                key=lambda item: (
                    -_BASE_CONFIDENCE[item.severity],
                    item.code,
                    item.summary,
                )
            )
            supporting_ids = tuple(
                sorted(
                    {
                        evidence_id
                        for finding in class_findings
                        for evidence_id in finding.evidence_ids
                        if evidence_id in allowed_evidence_ids
                    }
                )
            )
            severity_base = max(_BASE_CONFIDENCE[item.severity] for item in class_findings)
            distinct_codes = {item.code for item in class_findings}
            confidence = min(0.90, severity_base + 0.045 * max(0, len(distinct_codes) - 1))
            status = HypothesisStatus.SUPPORTED
            if not supporting_ids:
                confidence = min(confidence, 0.30)
                status = HypothesisStatus.LOW_EVIDENCE

            contexts = find_context_runbooks(fault_class, tuple(class_findings), hits)
            summaries = " ".join(item.summary for item in class_findings)
            rationale = (
                f"Derived from {len(class_findings)} deterministic finding(s) across "
                f"{len(distinct_codes)} finding code(s). "
            )
            if supporting_ids:
                rationale += (
                    f"{len(supporting_ids)} incident evidence record(s) resolve to this "
                    "hypothesis. "
                )
            else:
                rationale += "No resolvable incident evidence directly supports this hypothesis. "
            if contexts:
                rationale += (
                    f"{len(contexts)} retrieved runbook chunk(s) provide operational context; "
                    "runbooks are guidance, not proof of this incident's cause. "
                )
            rationale += "This is a ranked hypothesis, not a confirmed root cause."

            class_affected = (
                affected_nodes
                if fault_class in {FaultClass.TASK_FAILURE, FaultClass.BROKEN_DEPENDENCY}
                else ()
            )
            hypotheses.append(
                RootCauseHypothesis(
                    fault_class=fault_class,
                    summary=summaries[:500],
                    confidence=confidence,
                    status=status,
                    supporting_evidence_ids=supporting_ids,
                    context_evidence_ids=contexts,
                    finding_codes=tuple(sorted(distinct_codes)),
                    affected_nodes=tuple(class_affected),
                    rationale=rationale,
                )
            )

        hypotheses.sort(
            key=lambda item: (
                -item.confidence,
                -len(item.supporting_evidence_ids),
                item.fault_class.value,
            )
        )
        return tuple(hypotheses[:max_hypotheses])
