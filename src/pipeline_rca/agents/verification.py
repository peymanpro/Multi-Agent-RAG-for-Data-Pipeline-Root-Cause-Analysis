"""Deterministic citation and provenance verification for agent outputs."""

from __future__ import annotations

from dataclasses import replace

from pipeline_rca.agents.models import (
    HypothesisStatus,
    RootCauseHypothesis,
    VerificationIssue,
)
from pipeline_rca.models import (
    DiagnosticFinding,
    EvidenceRecord,
    Severity,
)


class EvidenceVerifierAgent:
    """Validate reference existence and keep observations separate from runbook context.

    This validator checks referential and provenance integrity, not semantic entailment:
    an identifier resolving to an observation does not alone prove that the observation
    entails every sentence in a generated hypothesis.
    """

    name = "evidence-verifier-agent"

    def sanitize_finding_references(
        self,
        findings: tuple[DiagnosticFinding, ...],
        evidence: tuple[EvidenceRecord, ...],
    ) -> tuple[DiagnosticFinding, ...]:
        """Remove finding references that are missing, ambiguous, or runbook-only."""
        by_id: dict[str, EvidenceRecord] = {}
        colliding_ids: set[str] = set()
        for item in evidence:
            existing = by_id.get(item.evidence_id)
            if existing is None:
                by_id[item.evidence_id] = item
            elif existing != item:
                colliding_ids.add(item.evidence_id)

        observation_ids = {
            evidence_id
            for evidence_id, item in by_id.items()
            if item.kind != "retrieved_document_chunk" and evidence_id not in colliding_ids
        }
        return tuple(
            replace(
                finding,
                evidence_ids=tuple(
                    dict.fromkeys(
                        evidence_id
                        for evidence_id in finding.evidence_ids
                        if evidence_id in observation_ids
                    )
                ),
            )
            for finding in findings
        )

    def verify(
        self,
        findings: tuple[DiagnosticFinding, ...],
        hypotheses: tuple[RootCauseHypothesis, ...],
        evidence: tuple[EvidenceRecord, ...],
    ) -> tuple[tuple[RootCauseHypothesis, ...], tuple[VerificationIssue, ...]]:
        """Flag dangling citations and demote any hypothesis with invalid references."""
        issues: list[VerificationIssue] = []
        by_id: dict[str, EvidenceRecord] = {}
        colliding_ids: set[str] = set()

        for item in evidence:
            existing = by_id.get(item.evidence_id)
            if existing is None:
                by_id[item.evidence_id] = item
            elif existing != item:
                colliding_ids.add(item.evidence_id)

        for evidence_id in sorted(colliding_ids):
            issues.append(
                VerificationIssue(
                    code="EVIDENCE_ID_COLLISION",
                    severity=Severity.ERROR,
                    summary=(
                        f"Evidence identifier {evidence_id!r} refers to conflicting records."
                    ),
                    evidence_ids=(evidence_id,),
                )
            )

        observation_ids = {
            evidence_id
            for evidence_id, item in by_id.items()
            if item.kind != "retrieved_document_chunk" and evidence_id not in colliding_ids
        }
        context_ids = {
            evidence_id
            for evidence_id, item in by_id.items()
            if item.kind == "retrieved_document_chunk" and evidence_id not in colliding_ids
        }

        for finding in findings:
            missing = tuple(
                sorted(set(finding.evidence_ids) - observation_ids - context_ids)
            )
            if missing:
                issues.append(
                    VerificationIssue(
                        code="FINDING_EVIDENCE_UNRESOLVED",
                        severity=Severity.ERROR,
                        summary=(
                            f"Finding {finding.code!r} refers to evidence that is not in "
                            "the approved evidence set."
                        ),
                        evidence_ids=missing,
                    )
                )
            retrieved_as_observation = tuple(
                sorted(set(finding.evidence_ids) & context_ids)
            )
            if retrieved_as_observation:
                issues.append(
                    VerificationIssue(
                        code="FINDING_USES_RUNBOOK_AS_OBSERVATION",
                        severity=Severity.WARNING,
                        summary=(
                            f"Finding {finding.code!r} cites general runbook context as if "
                            "it were incident-specific evidence."
                        ),
                        evidence_ids=retrieved_as_observation,
                    )
                )

        verified: list[RootCauseHypothesis] = []
        for hypothesis in hypotheses:
            invalid_support = tuple(
                sorted(set(hypothesis.supporting_evidence_ids) - observation_ids)
            )
            invalid_contradiction = tuple(
                sorted(set(hypothesis.contradicting_evidence_ids) - observation_ids)
            )
            invalid_context = tuple(
                sorted(set(hypothesis.context_evidence_ids) - context_ids)
            )
            all_invalid = tuple(
                sorted(set(invalid_support + invalid_contradiction + invalid_context))
            )

            if invalid_support:
                issues.append(
                    VerificationIssue(
                        code="HYPOTHESIS_SUPPORT_REFERENCE_INVALID",
                        severity=Severity.ERROR,
                        summary=(
                            f"Hypothesis {hypothesis.fault_class.value!r} cites support "
                            "that is not an approved incident observation."
                        ),
                        evidence_ids=invalid_support,
                    )
                )
            if invalid_contradiction:
                issues.append(
                    VerificationIssue(
                        code="HYPOTHESIS_COUNTEREVIDENCE_REFERENCE_INVALID",
                        severity=Severity.ERROR,
                        summary=(
                            f"Hypothesis {hypothesis.fault_class.value!r} cites invalid "
                            "counter-evidence."
                        ),
                        evidence_ids=invalid_contradiction,
                    )
                )
            if invalid_context:
                issues.append(
                    VerificationIssue(
                        code="HYPOTHESIS_CONTEXT_REFERENCE_INVALID",
                        severity=Severity.ERROR,
                        summary=(
                            f"Hypothesis {hypothesis.fault_class.value!r} cites context "
                            "that is not a retrieved runbook chunk."
                        ),
                        evidence_ids=invalid_context,
                    )
                )

            if all_invalid:
                verified.append(
                    replace(
                        hypothesis,
                        confidence=min(hypothesis.confidence, 0.20),
                        status=HypothesisStatus.UNVERIFIED,
                        supporting_evidence_ids=tuple(
                            item
                            for item in hypothesis.supporting_evidence_ids
                            if item in observation_ids
                        ),
                        contradicting_evidence_ids=tuple(
                            item
                            for item in hypothesis.contradicting_evidence_ids
                            if item in observation_ids
                        ),
                        context_evidence_ids=tuple(
                            item
                            for item in hypothesis.context_evidence_ids
                            if item in context_ids
                        ),
                        rationale=(
                            hypothesis.rationale
                            + " Verification demoted this hypothesis because one or more "
                            "evidence references did not satisfy the provenance contract."
                        ),
                    )
                )
                continue

            if not hypothesis.supporting_evidence_ids:
                verified.append(
                    replace(
                        hypothesis,
                        confidence=min(hypothesis.confidence, 0.30),
                        status=HypothesisStatus.LOW_EVIDENCE,
                    )
                )
            else:
                verified.append(hypothesis)

        issues.sort(key=lambda issue: (issue.code, issue.summary, issue.evidence_ids))
        return tuple(verified), tuple(issues)
