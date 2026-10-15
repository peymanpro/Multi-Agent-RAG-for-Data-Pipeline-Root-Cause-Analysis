"""Schema and required-column diagnostics."""

from pipeline_rca.models import (
    DiagnosticFinding,
    FaultClass,
    IncidentCase,
    SchemaSnapshot,
    Severity,
)


def _evidence_ids(snapshot: SchemaSnapshot) -> tuple[str, ...]:
    return (snapshot.evidence_id,) if snapshot.evidence_id else ()


def diagnose_schema(case: IncidentCase) -> tuple[DiagnosticFinding, ...]:
    """Find duplicate and missing required columns in observed schema snapshots."""
    findings: list[DiagnosticFinding] = []

    for snapshot in case.schemas:
        duplicates = sorted(
            column for column in set(snapshot.columns) if snapshot.columns.count(column) > 1
        )
        if duplicates:
            findings.append(
                DiagnosticFinding(
                    code="SCHEMA_DUPLICATE_COLUMN",
                    fault_class=FaultClass.SCHEMA_DRIFT,
                    severity=Severity.ERROR,
                    summary=(
                        f"Dataset {snapshot.dataset!r} declares duplicate column names: "
                        f"{', '.join(duplicates)}."
                    ),
                    evidence_ids=_evidence_ids(snapshot),
                    observed=", ".join(duplicates),
                    expected="unique column names",
                )
            )

        missing = sorted(set(snapshot.required_columns) - set(snapshot.columns))
        if missing:
            findings.append(
                DiagnosticFinding(
                    code="SCHEMA_REQUIRED_COLUMN_MISSING",
                    fault_class=FaultClass.SCHEMA_DRIFT,
                    severity=Severity.CRITICAL,
                    summary=(
                        f"Dataset {snapshot.dataset!r} is missing required columns: "
                        f"{', '.join(missing)}."
                    ),
                    evidence_ids=_evidence_ids(snapshot),
                    observed=", ".join(snapshot.columns),
                    expected=", ".join(snapshot.required_columns),
                )
            )

    return tuple(findings)
