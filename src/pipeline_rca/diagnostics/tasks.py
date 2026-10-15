"""Pipeline task status diagnostics."""

from pipeline_rca.models import (
    DiagnosticFinding,
    FaultClass,
    IncidentCase,
    Severity,
    TaskStatus,
)


def diagnose_tasks(case: IncidentCase) -> tuple[DiagnosticFinding, ...]:
    """Turn failed task observations into traceable deterministic findings."""
    findings: list[DiagnosticFinding] = []

    for task in case.tasks:
        if task.status == TaskStatus.FAILED:
            evidence_ids = (task.evidence_id,) if task.evidence_id else ()
            message = f": {task.message}" if task.message else "."
            findings.append(
                DiagnosticFinding(
                    code="PIPELINE_TASK_FAILED",
                    fault_class=FaultClass.TASK_FAILURE,
                    severity=Severity.ERROR,
                    summary=f"Pipeline task {task.task_id!r} failed{message}",
                    evidence_ids=evidence_ids,
                    observed=task.status.value,
                    expected=TaskStatus.SUCCESS.value,
                )
            )

    return tuple(findings)
