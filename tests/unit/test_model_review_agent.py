import json

import pytest

from pipeline_rca.agents.model_review import ModelCounterEvidenceReviewer, ModelReviewError
from pipeline_rca.agents.models import AgentBudget, HypothesisStatus, RootCauseHypothesis
from pipeline_rca.models import EvidenceRecord, FaultClass, IncidentCase


class FakeChatModel:
    def __init__(self, response: str) -> None:
        self.response = response
        self.user_prompt = ""

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1_000,
    ) -> str:
        assert system_prompt
        assert temperature == 0.0
        assert max_tokens == 1_000
        self.user_prompt = user_prompt
        return self.response


def _inputs() -> tuple[IncidentCase, tuple[RootCauseHypothesis, ...], tuple[EvidenceRecord, ...]]:
    case = IncidentCase(case_id="review-001", question="Why did schema validation fail?")
    hypothesis = RootCauseHypothesis(
        fault_class=FaultClass.SCHEMA_DRIFT,
        summary="A required column is missing.",
        confidence=0.8,
        status=HypothesisStatus.SUPPORTED,
        supporting_evidence_ids=("ev-observed",),
    )
    evidence = (
        EvidenceRecord(
            evidence_id="ev-observed",
            source="schema-registry",
            locator="orders/schema",
            summary="The required column was not observed.",
            kind="schema_snapshot",
        ),
        EvidenceRecord(
            evidence_id="ev-counter",
            source="contract-log",
            locator="orders/consumer",
            summary="The consumer contract requires a different column.",
            kind="contract_observation",
        ),
        EvidenceRecord(
            evidence_id="chunk-runbook",
            source="file:schema-drift.md",
            locator="lines:1-4#Symptoms",
            summary="General instructions for schema drift.",
            kind="retrieved_document_chunk",
        ),
    )
    return case, (hypothesis,), evidence


def test_downgrade_decision_lowers_confidence_without_claiming_an_alternate_cause() -> None:
    model = FakeChatModel(
        json.dumps(
            {
                "reviews": [
                    {
                        "fault_class": "schema_drift",
                        "decision": "downgrade",
                        "counter_evidence_ids": [],
                        "rationale": "The source and consumer timestamps were not aligned.",
                    }
                ]
            }
        )
    )
    case, hypotheses, evidence = _inputs()

    result = ModelCounterEvidenceReviewer(model).run(
        case, hypotheses, evidence, budget=AgentBudget()
    )

    assert result[0].status == HypothesisStatus.LOW_EVIDENCE
    assert result[0].confidence <= 0.35
    assert "Independent model review decision: downgrade" in result[0].rationale
    assert "chunk-runbook" not in model.user_prompt


def test_counter_evidence_must_be_an_observation_and_is_kept_separate() -> None:
    model = FakeChatModel(
        json.dumps(
            {
                "reviews": [
                    {
                        "fault_class": "schema_drift",
                        "decision": "retain",
                        "counter_evidence_ids": ["ev-counter"],
                        "rationale": "A second observation makes the explanation less certain.",
                    }
                ]
            }
        )
    )
    case, hypotheses, evidence = _inputs()

    result = ModelCounterEvidenceReviewer(model).run(
        case, hypotheses, evidence, budget=AgentBudget()
    )

    assert result[0].status == HypothesisStatus.LOW_EVIDENCE
    assert result[0].contradicting_evidence_ids == ("ev-counter",)
    assert result[0].confidence <= 0.60


def test_reviewer_cannot_invent_or_cite_runbook_ids_as_counter_evidence() -> None:
    case, hypotheses, evidence = _inputs()
    for fake_id in ("invented-id", "chunk-runbook"):
        model = FakeChatModel(
            json.dumps(
                {
                    "reviews": [
                        {
                            "fault_class": "schema_drift",
                            "decision": "downgrade",
                            "counter_evidence_ids": [fake_id],
                            "rationale": "This reference is not eligible counter-evidence.",
                        }
                    ]
                }
            )
        )
        with pytest.raises(ModelReviewError, match="not shown to the reviewer"):
            ModelCounterEvidenceReviewer(model).run(
                case, hypotheses, evidence, budget=AgentBudget()
            )


def test_review_must_cover_each_hypothesis_with_a_valid_decision() -> None:
    case, hypotheses, evidence = _inputs()
    model = FakeChatModel(
        json.dumps(
            {
                "reviews": [
                    {
                        "fault_class": "schema_drift",
                        "decision": [],
                        "counter_evidence_ids": [],
                        "rationale": "Invalid decision type.",
                    }
                ]
            }
        )
    )
    with pytest.raises(ModelReviewError, match="invalid decision"):
        ModelCounterEvidenceReviewer(model).run(
            case, hypotheses, evidence, budget=AgentBudget()
        )
