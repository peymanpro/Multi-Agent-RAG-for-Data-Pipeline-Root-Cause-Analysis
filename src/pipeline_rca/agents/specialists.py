"""Deterministic specialist agents that gather structured incident evidence."""

from __future__ import annotations

from datetime import datetime

from pipeline_rca.agents.models import AgentBudget
from pipeline_rca.diagnostics.data_quality import diagnose_data_quality
from pipeline_rca.diagnostics.schema import diagnose_schema
from pipeline_rca.diagnostics.tasks import diagnose_tasks
from pipeline_rca.lineage import LineageGraph
from pipeline_rca.models import (
    DiagnosticFinding,
    FaultClass,
    IncidentCase,
    Severity,
)
from pipeline_rca.retrieval.corpus import MarkdownCorpus
from pipeline_rca.retrieval.lexical import tokenize
from pipeline_rca.retrieval.models import RetrievalHit


class SchemaInvestigator:
    """Checks observed schema snapshots against declared column contracts."""

    name = "schema-investigator"

    def run(self, case: IncidentCase) -> tuple[DiagnosticFinding, ...]:
        return diagnose_schema(case)


class DataQualityInvestigator:
    """Checks row counts, duplicates, nulls, and configured freshness limits."""

    name = "data-quality-investigator"

    def run(
        self, case: IncidentCase, *, as_of: datetime | None = None
    ) -> tuple[DiagnosticFinding, ...]:
        return diagnose_data_quality(case, as_of=as_of)


class TaskFailureInvestigator:
    """Interprets task outcomes as operational observations."""

    name = "task-failure-investigator"

    def run(self, case: IncidentCase) -> tuple[DiagnosticFinding, ...]:
        return diagnose_tasks(case)


class LineageInvestigator:
    """Finds dependency cycles and computes potential downstream impact."""

    name = "lineage-investigator"

    def run(
        self, case: IncidentCase
    ) -> tuple[tuple[DiagnosticFinding, ...], tuple[str, ...]]:
        graph = LineageGraph(case.lineage)
        findings: list[DiagnosticFinding] = []

        for cycle in graph.cycles():
            cycle_nodes = set(cycle)
            cycle_evidence = tuple(
                sorted(
                    {
                        edge.evidence_id
                        for edge in case.lineage
                        if edge.evidence_id
                        and edge.upstream in cycle_nodes
                        and edge.downstream in cycle_nodes
                    }
                )
            )
            path = " -> ".join((*cycle, cycle[0]))
            findings.append(
                DiagnosticFinding(
                    code="LINEAGE_CYCLE_DETECTED",
                    fault_class=FaultClass.BROKEN_DEPENDENCY,
                    severity=Severity.ERROR,
                    summary=f"Lineage contains a directed cycle: {path}.",
                    evidence_ids=cycle_evidence,
                    observed=path,
                    expected="acyclic dependency graph",
                )
            )

        affected: set[str] = set()
        failed_task_ids = {
            task.task_id for task in case.tasks if task.status.value == "failed"
        }
        for task_id in sorted(failed_task_ids):
            affected.update(graph.downstream_of(task_id))

        return tuple(findings), tuple(sorted(affected))


class RunbookRetrievalInvestigator:
    """Retrieves operational guidance and retains exact source provenance."""

    name = "runbook-retrieval-investigator"

    def run(
        self,
        case: IncidentCase,
        findings: tuple[DiagnosticFinding, ...],
        *,
        corpus: MarkdownCorpus | None,
        budget: AgentBudget,
    ) -> tuple[RetrievalHit, ...]:
        if corpus is None:
            return ()

        pieces = [case.question]
        for finding in findings:
            pieces.extend((finding.code, finding.fault_class.value, finding.summary))
        query = " ".join(pieces)[: budget.max_prompt_chars]
        if not query.strip():
            return ()
        return corpus.search(query, top_k=budget.max_retrieval_hits)


def find_context_runbooks(
    fault_class: FaultClass,
    findings: tuple[DiagnosticFinding, ...],
    hits: tuple[RetrievalHit, ...],
) -> tuple[str, ...]:
    """Return retrieval chunk IDs with lexical overlap to a specific fault hypothesis.

    Runbooks are operational guidance, not direct proof of an incident's cause; callers
    should store these references separately from observation-based supporting evidence.
    """
    class_terms = set(tokenize(fault_class.value.replace("_", " ")))
    relevant_findings = [item for item in findings if item.fault_class == fault_class]
    for finding in relevant_findings:
        class_terms.update(tokenize(finding.code.replace("_", " ")))
        class_terms.update(tokenize(finding.summary))

    scored: list[tuple[int, float, str]] = []
    for hit in hits:
        chunk_terms = set(tokenize(hit.chunk.text))
        overlap = len(class_terms & chunk_terms)
        if overlap:
            scored.append((overlap, hit.score, hit.chunk.chunk_id))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return tuple(chunk_id for _, _, chunk_id in scored[:3])
