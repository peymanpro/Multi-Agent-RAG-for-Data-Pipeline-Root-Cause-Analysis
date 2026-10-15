"""Deterministic investigation entry point."""

from datetime import datetime

from pipeline_rca.diagnostics import (
    diagnose_data_quality,
    diagnose_schema,
    diagnose_tasks,
)
from pipeline_rca.lineage import LineageGraph
from pipeline_rca.models import (
    DiagnosticFinding,
    FaultClass,
    IncidentCase,
    InvestigationReport,
    Severity,
    TaskStatus,
)


def analyze_case(
    case: IncidentCase, *, as_of: datetime | None = None
) -> InvestigationReport:
    """Run model-independent checks and assemble an evidence-linked report.

    This function reports symptoms and deterministic rule violations. It does not claim
    that the most severe finding is the confirmed causal root cause.
    """
    findings: list[DiagnosticFinding] = []
    findings.extend(diagnose_schema(case))
    findings.extend(diagnose_data_quality(case, as_of=as_of))
    findings.extend(diagnose_tasks(case))

    graph = LineageGraph(case.lineage)
    for cycle in graph.cycles():
        findings.append(
            DiagnosticFinding(
                code="LINEAGE_CYCLE_DETECTED",
                fault_class=FaultClass.BROKEN_DEPENDENCY,
                severity=Severity.ERROR,
                summary=f"Lineage contains a directed cycle: {' -> '.join((*cycle, cycle[0]))}.",
                evidence_ids=(),
                observed=" -> ".join((*cycle, cycle[0])),
                expected="acyclic dependency graph",
            )
        )

    affected: set[str] = set()
    for task in case.tasks:
        if task.status == TaskStatus.FAILED:
            affected.update(graph.downstream_of(task.task_id))

    findings.sort(key=lambda item: (item.code, item.summary, item.evidence_ids))
    status = "findings" if findings else "no_deterministic_findings"
    return InvestigationReport(
        case_id=case.case_id,
        findings=tuple(findings),
        affected_nodes=tuple(sorted(affected)),
        status=status,
    )
