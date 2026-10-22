from pipeline_rca.agents.models import HypothesisStatus, RootCauseHypothesis
from pipeline_rca.agents.verification import EvidenceVerifierAgent
from pipeline_rca.models import (
    DiagnosticFinding,
    EvidenceRecord,
    FaultClass,
    Severity,
)


def test_runbook_chunks_cannot_be_used_as_incident_support() -> None:
    evidence = (
        EvidenceRecord(
            evidence_id="ev-log-1",
            source="task-log",
            locator="run/1",
            summary="The task failed.",
            kind="task_run",
        ),
        EvidenceRecord(
            evidence_id="chunk-runbook-1",
            source="file:task-failure-and-lineage.md",
            locator="lines:1-5#Symptoms",
            summary="A producer task may affect downstream consumers.",
            kind="retrieved_document_chunk",
        ),
    )
    hypothesis = RootCauseHypothesis(
        fault_class=FaultClass.TASK_FAILURE,
        summary="A failed producer caused the incident.",
        confidence=0.8,
        status=HypothesisStatus.SUPPORTED,
        supporting_evidence_ids=("chunk-runbook-1",),
        context_evidence_ids=("ev-log-1",),
    )

    verified, issues = EvidenceVerifierAgent().verify((), (hypothesis,), evidence)

    assert verified[0].status == HypothesisStatus.UNVERIFIED
    assert verified[0].confidence <= 0.20
    assert verified[0].supporting_evidence_ids == ()
    assert {issue.code for issue in issues} == {
        "HYPOTHESIS_SUPPORT_REFERENCE_INVALID",
        "HYPOTHESIS_CONTEXT_REFERENCE_INVALID",
    }


def test_dangling_diagnostic_evidence_is_flagged() -> None:
    finding = DiagnosticFinding(
        code="TEST_FINDING",
        fault_class=FaultClass.SCHEMA_DRIFT,
        severity=Severity.ERROR,
        summary="An observation should be present.",
        evidence_ids=("missing-id",),
    )

    _, issues = EvidenceVerifierAgent().verify((finding,), (), ())

    assert len(issues) == 1
    assert issues[0].code == "FINDING_EVIDENCE_UNRESOLVED"
    assert issues[0].evidence_ids == ("missing-id",)


def test_conflicting_records_with_same_id_are_reported() -> None:
    evidence = (
        EvidenceRecord("same", "source-a", "loc", "first", "task_run"),
        EvidenceRecord("same", "source-b", "loc", "second", "task_run"),
    )

    _, issues = EvidenceVerifierAgent().verify((), (), evidence)

    assert any(issue.code == "EVIDENCE_ID_COLLISION" for issue in issues)



def test_finding_sanitization_keeps_only_unambiguous_observation_references() -> None:
    evidence = (
        EvidenceRecord(
            "valid-observation", "schema", "orders/v2", "Observed schema.", "schema_snapshot"
        ),
        EvidenceRecord(
            "runbook-only", "file:runbook.md", "lines:1-2", "General guidance.",
            "retrieved_document_chunk",
        ),
        EvidenceRecord("collision", "source-a", "loc", "first", "task_run"),
        EvidenceRecord("collision", "source-b", "loc", "second", "task_run"),
    )
    finding = DiagnosticFinding(
        code="TEST_FINDING",
        fault_class=FaultClass.SCHEMA_DRIFT,
        severity=Severity.ERROR,
        summary="A finding with mixed-quality references.",
        evidence_ids=("valid-observation", "missing-id", "runbook-only", "collision"),
    )

    sanitized = EvidenceVerifierAgent().sanitize_finding_references((finding,), evidence)

    assert sanitized[0].evidence_ids == ("valid-observation",)
