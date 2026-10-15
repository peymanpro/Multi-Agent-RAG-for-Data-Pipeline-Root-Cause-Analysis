"""Bounded orchestration for deterministic specialists, RAG, synthesis, and verification."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from time import perf_counter

from pipeline_rca.agents.model_gateway import ChatModel
from pipeline_rca.agents.model_synthesis import HypothesisAgentError, ModelHypothesisAgent
from pipeline_rca.agents.model_review import ModelCounterEvidenceReviewer, ModelReviewError
from pipeline_rca.agents.models import (
    AgentBudget,
    AgentTraceEvent,
    InvestigationResult,
    InvestigationStatus,
    RootCauseHypothesis,
    VerificationIssue,
    HypothesisStatus,
)
from pipeline_rca.agents.specialists import (
    DataQualityInvestigator,
    LineageInvestigator,
    RunbookRetrievalInvestigator,
    SchemaInvestigator,
    TaskFailureInvestigator,
)
from pipeline_rca.agents.synthesis import DeterministicHypothesisAgent
from pipeline_rca.agents.verification import EvidenceVerifierAgent
from pipeline_rca.models import EvidenceRecord, IncidentCase, Severity
from pipeline_rca.retrieval.corpus import MarkdownCorpus
from pipeline_rca.retrieval.models import RetrievalHit


class InvestigationOrchestrator:
    """Run specialist agents under explicit limits and always reserve verification."""

    def __init__(
        self,
        *,
        corpus: MarkdownCorpus | None = None,
        model: ChatModel | None = None,
        budget: AgentBudget | None = None,
    ) -> None:
        self._corpus = corpus
        self._budget = budget or AgentBudget()
        self._model_agent = ModelHypothesisAgent(model) if model is not None else None
        self._review_agent = ModelCounterEvidenceReviewer(model) if model is not None else None
        self._schema_agent = SchemaInvestigator()
        self._quality_agent = DataQualityInvestigator()
        self._task_agent = TaskFailureInvestigator()
        self._lineage_agent = LineageInvestigator()
        self._retrieval_agent = RunbookRetrievalInvestigator()
        self._deterministic_hypothesis_agent = DeterministicHypothesisAgent()
        self._verifier = EvidenceVerifierAgent()

    def run(
        self, case: IncidentCase, *, as_of: datetime | None = None
    ) -> InvestigationResult:
        """Investigate a single observable case and return a source-auditable report."""
        if len(case.evidence) > self._budget.max_evidence_records:
            raise ValueError(
                "case evidence exceeds max_evidence_records; reduce the case or raise the budget"
            )

        findings = []
        affected_nodes: tuple[str, ...] = ()
        hits: tuple[RetrievalHit, ...] = ()
        evidence: list[EvidenceRecord] = list(case.evidence)
        hypotheses: tuple[RootCauseHypothesis, ...] = ()
        issues: list[VerificationIssue] = []
        trace: list[AgentTraceEvent] = []
        executed_steps = 0
        partial = False
        budget_exhausted = False
        model_assisted = False
        model_reviewed = False
        model_calls = 0
        synthesis_detail = "Ranked hypotheses from deterministic findings."
        review_detail = "Model review was not configured."

        def current_synthesis_detail() -> str:
            return synthesis_detail

        def current_review_detail() -> str:
            return review_detail

        def execute(
            *,
            agent: str,
            action: str,
            fallback_detail: str,
            operation: Callable[[], None],
            input_refs: tuple[str, ...] = (),
            detail_provider: Callable[[], str] | None = None,
        ) -> bool:
            nonlocal executed_steps, partial
            executed_steps += 1
            started = perf_counter()
            status = "completed"
            detail = fallback_detail
            try:
                operation()
                if detail_provider is not None:
                    detail = detail_provider()
            except Exception as exc:
                status = "error"
                partial = True
                detail = f"Agent step failed ({type(exc).__name__}); later safe steps will continue."
                issues.append(
                    VerificationIssue(
                        code="AGENT_EXECUTION_FAILED",
                        severity=Severity.ERROR,
                        summary=f"Agent {agent!r} could not complete action {action!r}.",
                    )
                )
            if agent == self._retrieval_agent.name:
                output_refs = tuple(hit.chunk.chunk_id for hit in hits)
            elif agent in {"hypothesis-synthesis-agent", "model-counterevidence-reviewer"}:
                output_refs = tuple(item.fault_class.value for item in hypotheses)
            elif agent == self._verifier.name:
                output_refs = tuple(f"issue:{issue.code}" for issue in issues)
            else:
                output_refs = tuple(sorted({finding.code for finding in findings}))
            trace.append(
                AgentTraceEvent(
                    sequence=len(trace) + 1,
                    agent=agent,
                    action=action,
                    status=status,
                    detail=detail,
                    input_refs=input_refs[:30],
                    output_refs=tuple(sorted(set(output_refs)))[:30],
                    elapsed_ms=round((perf_counter() - started) * 1_000, 3),
                )
            )
            return status == "completed"

        def run_schema() -> None:
            findings.extend(self._schema_agent.run(case))

        def run_quality() -> None:
            findings.extend(self._quality_agent.run(case, as_of=as_of))

        def run_tasks() -> None:
            findings.extend(self._task_agent.run(case))

        def run_lineage() -> None:
            nonlocal affected_nodes
            lineage_findings, affected_nodes = self._lineage_agent.run(case)
            findings.extend(lineage_findings)

        def run_retrieval() -> None:
            nonlocal hits
            free_slots = self._budget.max_evidence_records - len(evidence)
            if self._corpus is None or free_slots <= 0:
                hits = ()
                return
            candidates = self._retrieval_agent.run(
                case,
                tuple(findings),
                corpus=self._corpus,
                budget=self._budget,
            )
            hits = candidates[:free_slots]
            evidence.extend(hit.chunk.to_evidence_record() for hit in hits)

        def run_synthesis() -> None:
            nonlocal hypotheses, model_assisted, synthesis_detail, model_calls
            available_evidence = tuple(evidence)
            if self._model_agent is not None and model_calls < self._budget.max_model_calls:
                model_calls += 1
                try:
                    hypotheses = self._model_agent.run(
                        case,
                        tuple(findings),
                        available_evidence,
                        hits,
                        affected_nodes,
                        budget=self._budget,
                    )
                    model_assisted = True
                    synthesis_detail = (
                        f"Model-assisted hypothesis agent returned {len(hypotheses)} "
                        "candidate(s); reported confidence is not calibrated."
                    )
                    return
                except HypothesisAgentError as exc:
                    issues.append(
                        VerificationIssue(
                            code="MODEL_HYPOTHESIS_FALLBACK",
                            severity=Severity.WARNING,
                            summary=(
                                "Model hypothesis output was rejected; deterministic "
                                f"synthesis was used ({type(exc).__name__})."
                            ),
                        )
                    )
                    synthesis_detail = (
                        "Model output failed the structured/evidence contract; "
                        "deterministic synthesis was used as a safe fallback."
                    )
            elif self._model_agent is not None:
                issues.append(
                    VerificationIssue(
                        code="MODEL_HYPOTHESIS_BUDGET_EXHAUSTED",
                        severity=Severity.WARNING,
                        summary="The per-investigation model-call budget prevented hypothesis generation.",
                    )
                )
                synthesis_detail = "Model hypothesis generation skipped because the model-call budget was exhausted."

            hypotheses = self._deterministic_hypothesis_agent.run(
                case,
                tuple(findings),
                available_evidence,
                hits,
                affected_nodes,
                max_hypotheses=self._budget.max_hypotheses,
            )

        def run_review() -> None:
            nonlocal hypotheses, model_reviewed, model_calls, review_detail
            if not hypotheses:
                review_detail = "No hypotheses were produced; model review was skipped."
                return
            if self._review_agent is None:
                return
            if model_calls >= self._budget.max_model_calls:
                issues.append(
                    VerificationIssue(
                        code="MODEL_REVIEW_BUDGET_EXHAUSTED",
                        severity=Severity.WARNING,
                        summary="The per-investigation model-call budget prevented counter-evidence review.",
                    )
                )
                review_detail = "Model review skipped because the model-call budget was exhausted."
                return

            model_calls += 1
            try:
                hypotheses = self._review_agent.run(
                    case, hypotheses, tuple(evidence), budget=self._budget
                )
            except ModelReviewError as exc:
                issues.append(
                    VerificationIssue(
                        code="MODEL_REVIEW_FALLBACK",
                        severity=Severity.WARNING,
                        summary=(
                            "Model review output was rejected; pre-review hypotheses were "
                            f"preserved ({type(exc).__name__})."
                        ),
                    )
                )
                review_detail = (
                    "Model review failed its structured/evidence contract; prior hypotheses "
                    "were preserved for the deterministic verifier."
                )
            else:
                model_reviewed = True
                review_detail = (
                    f"Independent model reviewer examined {len(hypotheses)} hypothesis(es); "
                    "review decisions remain advisory."
                )

        plan: tuple[tuple[str, str, str, Callable[[], None], tuple[str, ...]], ...] = (
            (
                "schema-investigator",
                "compare-schema-contracts",
                f"Checked {len(case.schemas)} schema snapshot(s).",
                run_schema,
                (case.case_id,),
            ),
            (
                "data-quality-investigator",
                "check-dataset-invariants",
                f"Checked {len(case.datasets)} dataset observation(s).",
                run_quality,
                (case.case_id,),
            ),
            (
                "task-failure-investigator",
                "inspect-task-outcomes",
                f"Checked {len(case.tasks)} task observation(s).",
                run_tasks,
                (case.case_id,),
            ),
            (
                "lineage-investigator",
                "trace-dependencies",
                f"Analyzed {len(case.lineage)} lineage edge(s).",
                run_lineage,
                (case.case_id,),
            ),
            (
                "runbook-retrieval-investigator",
                "retrieve-operational-guidance",
                "Searched the local runbook corpus.",
                run_retrieval,
                (case.case_id,),
            ),
            (
                "hypothesis-synthesis-agent",
                "rank-candidate-causes",
                synthesis_detail,
                run_synthesis,
                (case.case_id,),
            ),
        )

        if self._review_agent is not None:
            plan = (
                *plan,
                (
                    self._review_agent.name,
                    "review-counterevidence",
                    review_detail,
                    run_review,
                    (case.case_id,),
                ),
            )

        regular_step_limit = self._budget.max_agent_steps - 1
        for agent, action, detail, operation, input_refs in plan:
            if executed_steps >= regular_step_limit:
                budget_exhausted = True
                trace.append(
                    AgentTraceEvent(
                        sequence=len(trace) + 1,
                        agent="investigation-supervisor",
                        action="enforce-agent-step-budget",
                        status="budget_exhausted",
                        detail=(
                            "Remaining investigation stages were skipped to preserve the "
                            "mandatory final evidence-verification step."
                        ),
                        input_refs=(case.case_id,),
                    )
                )
                break
            if agent == "hypothesis-synthesis-agent":
                detail_provider = current_synthesis_detail
            elif agent == "model-counterevidence-reviewer":
                detail_provider = current_review_detail
            else:
                detail_provider = None
            execute(
                agent=agent,
                action=action,
                fallback_detail=detail,
                operation=operation,
                input_refs=input_refs,
                detail_provider=detail_provider,
            )

        verified_hypotheses: tuple[RootCauseHypothesis, ...] = hypotheses
        verified = False

        def verify_output() -> None:
            nonlocal verified_hypotheses, verified
            verified_hypotheses, verifier_issues = self._verifier.verify(
                tuple(findings), hypotheses, tuple(evidence)
            )
            issues.extend(verifier_issues)
            verified = True

        execute(
            agent=self._verifier.name,
            action="validate-evidence-references",
            fallback_detail="Checked every diagnostic and hypothesis evidence reference.",
            operation=verify_output,
            input_refs=(case.case_id,),
        )
        if not verified:
            verified_hypotheses = tuple(
                RootCauseHypothesis(
                    fault_class=item.fault_class,
                    summary=item.summary,
                    confidence=min(item.confidence, 0.20),
                    status=HypothesisStatus.UNVERIFIED,
                    supporting_evidence_ids=(),
                    contradicting_evidence_ids=(),
                    context_evidence_ids=(),
                    finding_codes=item.finding_codes,
                    affected_nodes=item.affected_nodes,
                    rationale=item.rationale
                    + " The final verifier failed, so this hypothesis is marked unverified.",
                )
                for item in hypotheses
            )

        findings.sort(key=lambda item: (item.code, item.summary, item.evidence_ids))
        issues.sort(key=lambda item: (item.code, item.summary, item.evidence_ids))
        if budget_exhausted:
            status = InvestigationStatus.BUDGET_EXHAUSTED
        elif partial:
            status = InvestigationStatus.PARTIAL
        elif verified_hypotheses:
            status = InvestigationStatus.COMPLETED
        else:
            status = InvestigationStatus.INSUFFICIENT_EVIDENCE

        return InvestigationResult(
            case_id=case.case_id,
            status=status,
            diagnostics=tuple(findings),
            hypotheses=verified_hypotheses,
            evidence=tuple(evidence),
            verification_issues=tuple(issues),
            affected_nodes=affected_nodes,
            trace=tuple(trace),
            model_assisted=model_assisted,
            model_reviewed=model_reviewed,
            model_calls=model_calls,
            budget_exhausted=budget_exhausted,
        )
