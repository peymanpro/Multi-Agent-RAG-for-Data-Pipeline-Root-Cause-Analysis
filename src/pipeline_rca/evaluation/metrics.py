"""Dependency-free metrics for multi-label diagnostic evaluation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class SetMetrics:
    """Micro-averaged set metrics with case-level exact-match rate."""

    true_positives: int
    false_positives: int
    false_negatives: int
    cases: int
    exact_matches: int
    precision: float
    recall: float
    f1: float
    exact_match_rate: float

    def to_dict(self) -> dict[str, int | float]:
        """Return JSON-compatible metric values."""
        return asdict(self)


def measure_sets(
    expected_sets: Iterable[set[str]], predicted_sets: Iterable[set[str]]
) -> SetMetrics:
    """Measure multi-label predictions with explicit empty-set semantics.

    If both expected and predicted sets are empty for the entire evaluation, precision,
    recall, F1, and exact-match rate are all 1.0. If only one side is empty, its relevant
    precision or recall is 0.0. Per-case exact match is retained alongside micro counts.
    """
    expected = [set(items) for items in expected_sets]
    predicted = [set(items) for items in predicted_sets]
    if len(expected) != len(predicted):
        raise ValueError("expected_sets and predicted_sets must have equal length")

    true_positives = 0
    false_positives = 0
    false_negatives = 0
    exact_matches = 0

    for truth, guess in zip(expected, predicted, strict=True):
        true_positives += len(truth & guess)
        false_positives += len(guess - truth)
        false_negatives += len(truth - guess)
        exact_matches += int(truth == guess)

    cases = len(expected)
    predicted_total = true_positives + false_positives
    expected_total = true_positives + false_negatives

    if predicted_total == 0:
        precision = 1.0 if expected_total == 0 else 0.0
    else:
        precision = true_positives / predicted_total

    if expected_total == 0:
        recall = 1.0 if predicted_total == 0 else 0.0
    else:
        recall = true_positives / expected_total

    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    exact_match_rate = exact_matches / cases if cases else 1.0

    return SetMetrics(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        cases=cases,
        exact_matches=exact_matches,
        precision=precision,
        recall=recall,
        f1=f1,
        exact_match_rate=exact_match_rate,
    )
