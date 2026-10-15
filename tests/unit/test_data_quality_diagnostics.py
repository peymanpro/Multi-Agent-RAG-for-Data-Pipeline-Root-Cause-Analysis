from datetime import UTC, datetime

import pytest

from pipeline_rca.diagnostics.data_quality import diagnose_data_quality
from pipeline_rca.models import DatasetObservation, FaultClass, IncidentCase


def test_row_count_duplicate_and_null_findings_keep_source_reference() -> None:
    case = IncidentCase(
        case_id="quality-001",
        question="Why is the model inconsistent?",
        datasets=(
            DatasetObservation(
                dataset="orders",
                row_count=90,
                expected_row_count=100,
                duplicate_key_count=3,
                null_count_by_column={"customer_id": 2},
                evidence_id="dataset-observation-1",
            ),
        ),
    )

    findings = diagnose_data_quality(case)

    assert {finding.code for finding in findings} == {
        "DATASET_ROW_COUNT_MISMATCH",
        "DATASET_DUPLICATE_KEYS",
        "DATASET_NULL_VALUES",
    }
    assert all(finding.evidence_ids == ("dataset-observation-1",) for finding in findings)
    assert {finding.fault_class for finding in findings} == {
        FaultClass.ROW_COUNT_MISMATCH,
        FaultClass.DUPLICATE_RECORDS,
        FaultClass.TRANSFORMATION_DEFECT,
    }


def test_freshness_is_checked_only_against_explicit_timezone_aware_time() -> None:
    case = IncidentCase(
        case_id="freshness-001",
        question="Is the input stale?",
        datasets=(
            DatasetObservation(
                dataset="events",
                latest_event_time="2026-10-15T10:00:00Z",
                freshness_threshold_seconds=60,
            ),
        ),
    )

    assert diagnose_data_quality(case) == ()

    findings = diagnose_data_quality(
        case,
        as_of=datetime(2026, 10, 15, 10, 2, tzinfo=UTC),
    )

    assert len(findings) == 1
    assert findings[0].code == "DATASET_STALE_INPUT"
    assert findings[0].observed == "120.000"


def test_naive_as_of_is_rejected() -> None:
    case = IncidentCase(case_id="bad-time", question="Test")
    with pytest.raises(ValueError, match="timezone-aware"):
        diagnose_data_quality(case, as_of=datetime(2026, 10, 15, 10, 0))


def test_naive_event_timestamp_is_rejected_when_freshness_is_evaluated() -> None:
    case = IncidentCase(
        case_id="bad-event-time",
        question="Test",
        datasets=(
            DatasetObservation(
                dataset="events",
                latest_event_time="2026-10-15T10:00:00",
                freshness_threshold_seconds=60,
            ),
        ),
    )
    with pytest.raises(ValueError, match="UTC offset"):
        diagnose_data_quality(
            case,
            as_of=datetime(2026, 10, 15, 10, 2, tzinfo=UTC),
        )
