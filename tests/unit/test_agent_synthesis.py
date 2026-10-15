from pipeline_rca.agents.models import HypothesisStatus
from pipeline_rca.agents.synthesis import DeterministicHypothesisAgent
from pipeline_rca.models import (
    DiagnosticFinding,
    EvidenceRecord,
    FaultClass,
    IncidentCase,
    Severity,
)


def test_hypothesis_ranking_requires_resolvable_incident_evidence() -> None:
    agent = DeterministicHypothesisAgent()
    case = IncidentCase(case_id="syn-001", question="Why did schema processing fail?")
    evidence = (
        EvidenceRecord(
            evidence_id="ev-schema",
            source="schema-registry",
            locator="orders/schema-v2",
            summary="The required customer identifier is missing.",
            kind="schema_snapshot",
        ),
    )
    findings = (
        DiagnosticFinding(
            code="SCHEMA_REQUIRED_COLUMN_MISSING",
            fault_class=FaultClass.SCHEMA_DRIFT,
            severity=Severity.CRITICAL,
            summary="A required column is missing.",
            evidence_ids=("ev-schema",),
        ),
        DiagnosticFinding(
            code="SCHEMA_DUPLICATE_COLUMN",
            fault_class=FaultClass.SCHEMA_DRIFT,
            severity=Severity.ERROR,
            summary="The schema repeats a column name.",
            evidence_ids=("ev-missing-from-approved-set",),
        ),
    )

    hypotheses = agent.run(case, findings, evidence, (), (), max_hypotheses=3)

    assert len(hypotheses) == 1
    assert hypotheses[0].fault_class == FaultClass.SCHEMA_DRIFT
    assert hypotheses[0].status == HypothesisStatus.SUPPORTED
    assert hypotheses[0].supporting_evidence_ids == ("ev-schema",)
    assert "not a confirmed root cause" in hypotheses[0].rationale


def test_hypothesis_without_resolvable_evidence_is_demoted() -> None:
    findings = (
        DiagnosticFinding(
            code="PIPELINE_TASK_FAILED",
            fault_class=FaultClass.TASK_FAILURE,
            severity=Severity.ERROR,
            summary="A task failed.",
            evidence_ids=("missing-evidence",),
        ),
    )

    hypotheses = DeterministicHypothesisAgent().run(
        IncidentCase(case_id="syn-002", question="Why?"),
        findings,
        (),
        (),
        (),
    )

    assert hypotheses[0].status == HypothesisStatus.LOW_EVIDENCE
    assert hypotheses[0].confidence <= 0.30
    assert hypotheses[0].supporting_evidence_ids == ()
