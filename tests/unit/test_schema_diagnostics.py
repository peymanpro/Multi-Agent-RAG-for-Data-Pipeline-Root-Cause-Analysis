from pipeline_rca.diagnostics.schema import diagnose_schema
from pipeline_rca.models import FaultClass, IncidentCase, SchemaSnapshot, Severity


def test_missing_required_columns_are_reported_with_provenance() -> None:
    case = IncidentCase(
        case_id="schema-001",
        question="Why did the model fail?",
        schemas=(
            SchemaSnapshot(
                dataset="orders",
                columns=("order_id", "amount"),
                required_columns=("order_id", "customer_id"),
                evidence_id="schema-observation-1",
            ),
        ),
    )

    findings = diagnose_schema(case)

    assert len(findings) == 1
    assert findings[0].code == "SCHEMA_REQUIRED_COLUMN_MISSING"
    assert findings[0].fault_class == FaultClass.SCHEMA_DRIFT
    assert findings[0].severity == Severity.CRITICAL
    assert findings[0].observed == "amount, order_id"
    assert findings[0].expected == "customer_id, order_id"
    assert findings[0].evidence_ids == ("schema-observation-1",)


def test_duplicate_column_names_are_detected_deterministically() -> None:
    case = IncidentCase(
        case_id="schema-002",
        question="Check schema",
        schemas=(
            SchemaSnapshot(dataset="events", columns=("id", "id", "timestamp")),
        ),
    )

    first = diagnose_schema(case)
    second = diagnose_schema(case)

    assert [finding.code for finding in first] == ["SCHEMA_DUPLICATE_COLUMN"]
    assert first == second


def test_valid_schema_produces_no_findings() -> None:
    case = IncidentCase(
        case_id="schema-003",
        question="Check schema",
        schemas=(
            SchemaSnapshot(
                dataset="users",
                columns=("id", "email"),
                required_columns=("id", "email"),
            ),
        ),
    )

    assert diagnose_schema(case) == ()
