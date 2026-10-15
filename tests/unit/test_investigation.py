from pipeline_rca.investigation import analyze_case
from pipeline_rca.models import (
    DatasetObservation,
    IncidentCase,
    LineageEdge,
    SchemaSnapshot,
    TaskObservation,
    TaskStatus,
)


def test_investigation_combines_findings_and_affected_nodes() -> None:
    case = IncidentCase(
        case_id="incident-001",
        question="Why is sales_report incomplete?",
        datasets=(
            DatasetObservation(
                dataset="fact_orders",
                row_count=90,
                expected_row_count=100,
                evidence_id="quality-evidence",
            ),
        ),
        schemas=(
            SchemaSnapshot(
                dataset="stg_orders",
                columns=("order_id",),
                required_columns=("order_id", "customer_id"),
                evidence_id="schema-evidence",
            ),
        ),
        tasks=(
            TaskObservation(
                task_id="load_orders",
                status=TaskStatus.FAILED,
                evidence_id="task-evidence",
                message="source timed out",
            ),
        ),
        lineage=(
            LineageEdge("load_orders", "stg_orders"),
            LineageEdge("stg_orders", "fact_orders"),
            LineageEdge("fact_orders", "sales_report"),
        ),
    )

    report = analyze_case(case)

    assert report.case_id == "incident-001"
    assert report.status == "findings"
    assert {finding.code for finding in report.findings} == {
        "DATASET_ROW_COUNT_MISMATCH",
        "PIPELINE_TASK_FAILED",
        "SCHEMA_REQUIRED_COLUMN_MISSING",
    }
    assert report.affected_nodes == ("fact_orders", "sales_report", "stg_orders")
    assert all(finding.fault_class.value != "confirmed_root_cause" for finding in report.findings)


def test_clean_case_reports_no_deterministic_findings() -> None:
    report = analyze_case(IncidentCase(case_id="clean-001", question="Check the pipeline"))

    assert report.status == "no_deterministic_findings"
    assert not report.has_findings
