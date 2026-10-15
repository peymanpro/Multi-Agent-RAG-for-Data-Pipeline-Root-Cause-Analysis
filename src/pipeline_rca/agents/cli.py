"""Command-line interface for bounded multi-agent investigation."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pipeline_rca.agents.model_gateway import OpenAICompatibleChatModel
from pipeline_rca.agents.models import AgentBudget
from pipeline_rca.agents.orchestrator import InvestigationOrchestrator
from pipeline_rca.agents.reporting import result_to_dict
from pipeline_rca.models import IncidentCase
from pipeline_rca.retrieval.corpus import MarkdownCorpus
from pipeline_rca.serialization import incident_case_from_mapping


def _parse_as_of(value: str) -> datetime:
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed


def main(argv: list[str] | None = None) -> int:
    """Run a bounded investigation for one observable incident-case JSON file."""
    parser = argparse.ArgumentParser(
        prog="pipeline-rca-investigate",
        description=(
            "Investigate a data-pipeline incident using specialist agents, runbook RAG, "
            "and a final evidence-reference verifier."
        ),
    )
    parser.add_argument("case", type=Path, help="observable incident-case JSON file")
    parser.add_argument(
        "--runbooks",
        type=Path,
        default=Path("data/runbooks"),
        help="local Markdown runbook directory (default: data/runbooks)",
    )
    parser.add_argument(
        "--no-runbooks",
        action="store_true",
        help="disable retrieval and run deterministic specialist investigation only",
    )
    parser.add_argument(
        "--with-model",
        action="store_true",
        help=(
            "enable optional model-assisted hypothesis generation "
            "from RCA_* environment variables"
        ),
    )
    parser.add_argument(
        "--as-of",
        type=_parse_as_of,
        help="explicit timezone-aware ISO-8601 time used for freshness checks",
    )
    parser.add_argument("--max-agent-steps", type=int, default=8)
    parser.add_argument("--max-retrieval-hits", type=int, default=5)
    parser.add_argument("--max-evidence-records", type=int, default=60)
    parser.add_argument("--max-hypotheses", type=int, default=5)
    parser.add_argument("--max-model-calls", type=int, default=2)
    parser.add_argument("--max-prompt-chars", type=int, default=12_000)
    parser.add_argument("--model-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--model-max-output-tokens", type=int, default=1_000)
    parser.add_argument("--output", type=Path, help="optional path for the JSON report")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.case.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("incident case JSON must be an object")
        case: IncidentCase = incident_case_from_mapping(payload)

        budget = AgentBudget(
            max_agent_steps=args.max_agent_steps,
            max_retrieval_hits=args.max_retrieval_hits,
            max_evidence_records=args.max_evidence_records,
            max_hypotheses=args.max_hypotheses,
            max_model_calls=args.max_model_calls,
            max_prompt_chars=args.max_prompt_chars,
            model_timeout_seconds=args.model_timeout_seconds,
            model_max_output_tokens=args.model_max_output_tokens,
        )
        corpus = None
        if not args.no_runbooks:
            corpus = MarkdownCorpus.from_directory(args.runbooks)
        model = (
            OpenAICompatibleChatModel.from_env(
                timeout_seconds=budget.model_timeout_seconds
            )
            if args.with_model
            else None
        )
        result = InvestigationOrchestrator(
            corpus=corpus,
            model=model,
            budget=budget,
        ).run(case, as_of=args.as_of)
        rendered = json.dumps(result_to_dict(result), indent=2, sort_keys=True) + "\n"
        if args.output is None:
            print(rendered, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"pipeline-rca-investigate: error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
