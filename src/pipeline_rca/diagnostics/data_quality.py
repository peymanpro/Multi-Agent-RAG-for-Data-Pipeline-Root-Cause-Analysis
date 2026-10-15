"""Deterministic dataset-level quality checks."""

from __future__ import annotations

from datetime import UTC, datetime

from pipeline_rca.models import (
    DatasetObservation,
    DiagnosticFinding,
    FaultClass,
    IncidentCase,
    Severity,
)


def _parse_timestamp(value: str) -> datetime:
    """Parse ISO-8601 timestamps and normalize UTC offsets."""
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a UTC offset: {value!r}")
    return parsed.astimezone(UTC)


def _evidence_ids(dataset: DatasetObservation) -> tuple[str, ...]:
    return (dataset.evidence_id,) if dataset.evidence_id else ()


def diagnose_data_quality(
    case: IncidentCase, *, as_of: datetime | None = None
) -> tuple[DiagnosticFinding, ...]:
    """Find duplicate keys, row-count mismatches, nulls, and stale datasets.

    Freshness checks are performed only when an explicit timezone-aware as_of value is
    supplied. This keeps benchmark results reproducible and avoids silent wall-clock use.
    """
    if as_of is not None and as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")

    findings: list[DiagnosticFinding] = []
    normalized_as_of = as_of.astimezone(timezone.utc) if as_of is not None else None

    for dataset in case.datasets:
        evidence_ids = _evidence_ids(dataset)

        if dataset.row_count is not None and dataset.row_count < 0:
            findings.append(
                DiagnosticFinding(
                    code="DATASET_NEGATIVE_ROW_COUNT",
                    fault_class=FaultClass.ROW_COUNT_MISMATCH,
                    severity=Severity.CRITICAL,
                    summary=f"Dataset {dataset.dataset!r} reports a negative row count.",
                    evidence_ids=evidence_ids,
                    observed=str(dataset.row_count),
                    expected="row_count >= 0",
                )
            )
        elif (
            dataset.row_count is not None
            and dataset.expected_row_count is not None
            and dataset.row_count != dataset.expected_row_count
        ):
            findings.append(
                DiagnosticFinding(
                    code="DATASET_ROW_COUNT_MISMATCH",
                    fault_class=FaultClass.ROW_COUNT_MISMATCH,
                    severity=Severity.ERROR,
                    summary=(
                        f"Dataset {dataset.dataset!r} contains {dataset.row_count} rows; "
                        f"{dataset.expected_row_count} were expected."
                    ),
                    evidence_ids=evidence_ids,
                    observed=str(dataset.row_count),
                    expected=str(dataset.expected_row_count),
                )
            )

        if dataset.duplicate_key_count < 0:
            findings.append(
                DiagnosticFinding(
                    code="DATASET_INVALID_DUPLICATE_COUNT",
                    fault_class=FaultClass.DUPLICATE_RECORDS,
                    severity=Severity.CRITICAL,
                    summary=f"Dataset {dataset.dataset!r} has an invalid negative duplicate count.",
                    evidence_ids=evidence_ids,
                    observed=str(dataset.duplicate_key_count),
                    expected="duplicate_key_count >= 0",
                )
            )
        elif dataset.duplicate_key_count > 0:
            findings.append(
                DiagnosticFinding(
                    code="DATASET_DUPLICATE_KEYS",
                    fault_class=FaultClass.DUPLICATE_RECORDS,
                    severity=Severity.ERROR,
                    summary=(
                        f"Dataset {dataset.dataset!r} has "
                        f"{dataset.duplicate_key_count} duplicate key(s)."
                    ),
                    evidence_ids=evidence_ids,
                    observed=str(dataset.duplicate_key_count),
                    expected="0",
                )
            )

        for column, null_count in sorted(dataset.null_count_by_column.items()):
            if null_count < 0:
                findings.append(
                    DiagnosticFinding(
                        code="DATASET_INVALID_NULL_COUNT",
                        fault_class=FaultClass.TRANSFORMATION_DEFECT,
                        severity=Severity.CRITICAL,
                        summary=(
                            f"Dataset {dataset.dataset!r} reports a negative null count "
                            f"for column {column!r}."
                        ),
                        evidence_ids=evidence_ids,
                        observed=str(null_count),
                        expected="null_count >= 0",
                    )
                )
            elif null_count > 0:
                findings.append(
                    DiagnosticFinding(
                        code="DATASET_NULL_VALUES",
                        fault_class=FaultClass.TRANSFORMATION_DEFECT,
                        severity=Severity.WARNING,
                        summary=(
                            f"Dataset {dataset.dataset!r} has {null_count} null value(s) "
                            f"in column {column!r}."
                        ),
                        evidence_ids=evidence_ids,
                        observed=str(null_count),
                        expected="0 when the column contract forbids nulls",
                    )
                )

        if (
            normalized_as_of is not None
            and dataset.latest_event_time is not None
            and dataset.freshness_threshold_seconds is not None
        ):
            if dataset.freshness_threshold_seconds < 0:
                findings.append(
                    DiagnosticFinding(
                        code="DATASET_INVALID_FRESHNESS_THRESHOLD",
                        fault_class=FaultClass.STALE_INPUT,
                        severity=Severity.CRITICAL,
                        summary=f"Dataset {dataset.dataset!r} has a negative freshness threshold.",
                        evidence_ids=evidence_ids,
                        observed=str(dataset.freshness_threshold_seconds),
                        expected="freshness_threshold_seconds >= 0",
                    )
                )
            else:
                latest = _parse_timestamp(dataset.latest_event_time)
                age_seconds = max(0.0, (normalized_as_of - latest).total_seconds())
                if age_seconds > dataset.freshness_threshold_seconds:
                    findings.append(
                        DiagnosticFinding(
                            code="DATASET_STALE_INPUT",
                            fault_class=FaultClass.STALE_INPUT,
                            severity=Severity.ERROR,
                            summary=(
                                f"Dataset {dataset.dataset!r} is stale by the configured "
                                f"freshness threshold."
                            ),
                            evidence_ids=evidence_ids,
                            observed=f"{age_seconds:.3f}",
                            expected=f"<= {dataset.freshness_threshold_seconds}",
                        )
                    )

    return tuple(findings)
