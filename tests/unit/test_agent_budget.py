import pytest

from pipeline_rca.agents.models import AgentBudget


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_agent_steps": 0},
        {"max_retrieval_hits": 0},
        {"max_evidence_records": 0},
        {"max_hypotheses": 0},
        {"max_model_calls": 0},
        {"max_prompt_chars": 0},
        {"model_max_output_tokens": 0},
        {"model_timeout_seconds": 0},
    ],
)
def test_non_positive_agent_budgets_are_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        AgentBudget(**kwargs)  # type: ignore[arg-type]
