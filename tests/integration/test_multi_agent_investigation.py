import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pipeline_rca.agents.models import AgentBudget, InvestigationStatus
from pipeline_rca.agents.orchestrator import InvestigationOrchestrator
from pipeline_rca.agents.reporting import result_to_dict
from pipeline_rca.models import IncidentCase
from pipeline_rca.retrieval.corpus import MarkdownCorpus
from pipeline_rca.serialization import incident_case_from_mapping


ROOT = Path(__file__).resolve().parents[2]
CASE_PATH = ROOT / "examples" / "cases" / "schema-drift.json"
RUNBOOK_PATH = ROOT / "data" / "runbooks"


class FakeChatModel:
    def __init__(self, response: str) -> None:
        self.response = response

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1_000,
    ) -> str:
        assert system_prompt
        assert user_prompt
        assert temperature == 0.0
        assert max_tokens == 1_000
        return self.response


def _load_case() -> IncidentCase:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    return incident_case_from_mapping(payload)


def test_multi_agent_investigation_retrieves_context_and_verifies_citations() -> None:
    case = _load_case()
    corpus = MarkdownCorpus.from_directory(RUNBOOK_PATH)
    result = InvestigationOrchestrator(corpus=corpus).run(
        case, as_of=datetime(2026, 10, 15, 10, 5, tzinfo=UTC)
    )

    assert result.status == InvestigationStatus.COMPLETED
    assert result.has_hypotheses
    assert {"SCHEMA_REQUIRED_COLUMN_MISSING", "PIPELINE_TASK_FAILED"} <= {
        finding.code for finding in result.diagnostics
    }
    assert {item.kind for item in result.evidence} >= {
        "schema_snapshot",
        "task_run",
        "retrieved_document_chunk",
    }
    evidence_by_id = {item.evidence_id: item for item in result.evidence}
    for hypothesis in result.hypotheses:
        assert set(hypothesis.supporting_evidence_ids) <= set(evidence_by_id)
        assert all(
            evidence_by_id[item].kind != "retrieved_document_chunk"
            for item in hypothesis.supporting_evidence_ids
        )
        assert all(
            evidence_by_id[item].kind == "retrieved_document_chunk"
            for item in hypothesis.context_evidence_ids
        )
        assert "not a confirmed root cause" in hypothesis.rationale
    assert not result.verification_issues
    assert result.trace[-1].agent == "evidence-verifier-agent"
    assert any(event.agent == "runbook-retrieval-investigator" for event in result.trace)


def test_invalid_model_output_falls_back_to_deterministic_hypotheses() -> None:
    result = InvestigationOrchestrator(
        model=FakeChatModel("not valid JSON"),
        budget=AgentBudget(),
    ).run(_load_case())

    assert result.status == InvestigationStatus.COMPLETED
    assert result.model_assisted is False
    assert result.has_hypotheses
    assert any(
        issue.code == "MODEL_HYPOTHESIS_FALLBACK"
        for issue in result.verification_issues
    )


def test_valid_model_output_is_still_checked_by_the_final_verifier() -> None:
    response = json.dumps(
        {
            "hypotheses": [
                {
                    "fault_class": "schema_drift",
                    "summary": "The observed source schema violates the consumer contract.",
                    "confidence": 0.82,
                    "supporting_evidence_ids": ["schema-snapshot-orders-v2"],
                    "contradicting_evidence_ids": [],
                    "context_evidence_ids": [],
                    "rationale": "The observed schema omits customer_id.",
                }
            ]
        }
    )
    result = InvestigationOrchestrator(model=FakeChatModel(response)).run(_load_case())

    assert result.model_assisted is True
    assert result.hypotheses[0].confidence == pytest.approx(0.82)
    assert result.hypotheses[0].status.value == "supported"
    assert not result.verification_issues


def test_step_budget_reserves_the_final_verifier() -> None:
    result = InvestigationOrchestrator(
        budget=AgentBudget(max_agent_steps=2)
    ).run(_load_case())

    assert result.status == InvestigationStatus.BUDGET_EXHAUSTED
    assert result.budget_exhausted is True
    assert result.trace[-1].agent == "evidence-verifier-agent"
    assert any(event.status == "budget_exhausted" for event in result.trace)
    assert not result.hypotheses


def test_oversized_case_evidence_is_rejected_before_agent_execution() -> None:
    case = _load_case()

    with pytest.raises(ValueError, match="exceeds max_evidence_records"):
        InvestigationOrchestrator(
            budget=AgentBudget(max_evidence_records=1)
        ).run(case)


def test_report_serialization_marks_confidence_as_uncalibrated() -> None:
    result = InvestigationOrchestrator().run(_load_case())
    report = result_to_dict(result)

    assert report["case_id"] == "example-schema-drift-001"
    assert report["hypotheses"]
    assert report["hypotheses"][0]["confidence_is_calibrated"] is False
    assert report["trace"][-1]["agent"] == "evidence-verifier-agent"
