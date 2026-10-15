import pytest

from pipeline_rca.evaluation.metrics import measure_sets


def test_micro_set_metrics_include_exact_match_rate() -> None:
    metrics = measure_sets(
        [{"schema_drift", "stale_input"}, {"task_failure"}, set()],
        [{"schema_drift"}, {"task_failure", "duplicate_records"}, set()],
    )

    assert metrics.true_positives == 2
    assert metrics.false_positives == 1
    assert metrics.false_negatives == 1
    assert metrics.exact_matches == 1
    assert metrics.precision == pytest.approx(2 / 3)
    assert metrics.recall == pytest.approx(2 / 3)
    assert metrics.f1 == pytest.approx(2 / 3)
    assert metrics.exact_match_rate == pytest.approx(1 / 3)


def test_all_empty_expected_and_predicted_sets_are_perfect_matches() -> None:
    metrics = measure_sets([set(), set()], [set(), set()])

    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1 == 1.0
    assert metrics.exact_match_rate == 1.0


def test_length_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="equal length"):
        measure_sets([{"schema_drift"}], [])
