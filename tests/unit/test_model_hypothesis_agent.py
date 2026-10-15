import json

import pytest

from pipeline_rca.agents.model_synthesis import (
    HypothesisAgentError,
    ModelHypothesisAgent,
)
from pipeline_rca.agents.models import AgentBudget, HypothesisStatus
from pipeline_rca.models import (
    DiagnosticFinding,
    EvidenceRecord,
    FaultClass,
    IncidentCase,
    Severity,
)


class FakeChatModel:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_system_prompt = ""
        self.last_user_prompt = ""
        self.calls = 0

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1_000,
    ) -> str:
        self.calls += 1
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        assert temperature == 0.0
        assert max_tokens == 1_000
        return self.response


def _case() -> tuple[IncidentCase, tuple[DiagnosticFinding, ...], tuple[EvidenceRecord, ...]]:
    case = IncidentCase(
        case_id="model-case-001",
        question="Why did schema validation fail?",
        evidence=(
            EvidenceRecord(
                evidence_id="ev-schema-1",
                source="schema-registry",
                locator="orders/v2",
                summary="Required customer_id column is absent.",
                kind="schema_snapshot",
            ),
        ),
    )
    finding = DiagnosticFinding(
        code="SCHEMA_REQUIRED_COLUMN_MISSING",
        fault_class=FaultClass.SCHEMA_DRIFT,
        severity=Severity.CRITICAL,
        summary="A required column is absent.",
        evidence_ids=("ev-schema-1",),
    )
    return case, (finding,), case.evidence


def test_valid_model_hypothesis_is_accepted_with_allowed_evidence() -> None:
    response = json.dumps(
        {
            "hypotheses": [
                {
                    "fault_class": "schema_drift",
                    "summary": "The source schema no longer satisfies the declared contract.",
                    "confidence": 0.83,
                    "supporting_evidence_ids": ["ev-schema-1"],
                    "contradicting_evidence_ids": [],
                    "context_evidence_ids": [],
                    "rationale": "The observed schema omits a required field.",
                }
            ]
        }
    )
    model = FakeChatModel(response)
    case, findings, evidence = _case()

    result = ModelHypothesisAgent(model).run(
        case, findings, evidence, (), (), budget=AgentBudget()
    )

    assert len(result) == 1
    assert result[0].status == HypothesisStatus.SUPPORTED
    assert result[0].confidence == pytest.approx(0.83)
    assert result[0].supporting_evidence_ids == ("ev-schema-1",)
    assert "not a calibrated probability" in result[0].rationale
    assert model.calls == 1
    assert "untrusted incident data" in model.last_system_prompt
    assert "ev-schema-1" in model.last_user_prompt


def test_model_cannot_invent_an_evidence_identifier() -> None:
    response = json.dumps(
        {
            "hypotheses": [
                {
                    "fault_class": "schema_drift",
                    "summary": "Schema changed.",
                    "confidence": 0.9,
                    "supporting_evidence_ids": ["made-up-reference"],
                    "contradicting_evidence_ids": [],
                    "context_evidence_ids": [],
                    "rationale": "The fabricated reference supposedly proves this.",
                }
            ]
        }
    )
    case, findings, evidence = _case()

    with pytest.raises(HypothesisAgentError, match="not available to the model"):
        ModelHypothesisAgent(FakeChatModel(response)).run(
            case, findings, evidence, (), (), budget=AgentBudget()
        )


def test_model_output_must_be_strict_json() -> None:
    case, findings, evidence = _case()

    with pytest.raises(HypothesisAgentError, match="valid JSON"):
        ModelHypothesisAgent(FakeChatModel("not JSON")).run(
            case, findings, evidence, (), (), budget=AgentBudget()
        )


def test_prompt_budget_is_enforced_without_invalidating_json() -> None:
    case, findings, evidence = _case()
    model = FakeChatModel(json.dumps({"hypotheses": []}))

    ModelHypothesisAgent(model).run(
        case,
        findings,
        evidence,
        (),
        (),
        budget=AgentBudget(max_prompt_chars=1_000),
    )

    assert len(model.last_user_prompt) <= 1_000
    json.loads(model.last_user_prompt)
