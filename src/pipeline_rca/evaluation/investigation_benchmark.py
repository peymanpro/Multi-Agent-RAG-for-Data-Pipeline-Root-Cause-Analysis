"""Leakage-aware evaluation of deterministic and multi-agent RCA baselines."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from pipeline_rca.agents.models import AgentBudget
from pipeline_rca.agents.orchestrator import InvestigationOrchestrator
from pipeline_rca.agents.reporting import result_to_dict
from pipeline_rca.evaluation.metrics import measure_sets
from pipeline_rca.investigation import analyze_case
from pipeline_rca.models import (
    DiagnosticFinding,
    FaultClass,
    IncidentCase,
    InvestigationReport,
)
from pipeline_rca.retrieval.corpus import MarkdownCorpus
from pipeline_rca.serialization import incident_case_from_mapping

_SEVERITY_RANK = {"critical": 4, "error": 3, "warning": 2, "info": 1}


def _read_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _safe_child(root: Path, relative: object, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError(f"{label} must be a non-empty relative path")
    root_resolved = root.resolve()
    candidate = (root_resolved / relative).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the benchmark directory") from exc
    if not candidate.is_file():
        raise ValueError(f"{label} does not identify a file: {relative}")
    return candidate


def _string_set(value: object, *, label: str) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    if any(not item.strip() for item in value):
        raise ValueError(f"{label} cannot contain empty strings")
    return set(value)


def _truth_payload(
    payload: dict[str, Any], *, case_id: str
) -> tuple[set[str], set[str], set[str]]:
    allowed = {
        "case_id",
        "expected_fault_classes",
        "expected_finding_codes",
        "expected_affected_nodes",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"Truth for {case_id!r} has unsupported fields: {', '.join(unknown)}")
    if payload.get("case_id") != case_id:
        raise ValueError(f"Truth case_id does not match {case_id!r}")

    expected_classes = _string_set(
        payload.get("expected_fault_classes"), label=f"{case_id}.expected_fault_classes"
    )
    expected_codes = _string_set(
        payload.get("expected_finding_codes"), label=f"{case_id}.expected_finding_codes"
    )
    expected_nodes = _string_set(
        payload.get("expected_affected_nodes"), label=f"{case_id}.expected_affected_nodes"
    )
    allowed_classes = {value.value for value in FaultClass}
    invalid_classes = sorted(expected_classes - allowed_classes)
    if invalid_classes:
        raise ValueError(f"Unknown fault classes in {case_id!r}: {', '.join(invalid_classes)}")
    return expected_classes, expected_codes, expected_nodes


def _rank_findings(findings: tuple[DiagnosticFinding, ...]) -> list[str]:
    strongest: dict[str, int] = {}
    for finding in findings:
        fault_class = finding.fault_class.value
        if finding.fault_class == FaultClass.UNKNOWN:
            continue
        rank = _SEVERITY_RANK[finding.severity.value]
        strongest[fault_class] = max(strongest.get(fault_class, 0), rank)
    return sorted(strongest, key=lambda value: (-strongest[value], value))


def _baseline_report_to_dict(report: InvestigationReport) -> dict[str, Any]:
    return {
        "diagnostics": [
            {
                "code": item.code,
                "fault_class": item.fault_class.value,
                "severity": item.severity.value,
                "evidence_ids": list(item.evidence_ids),
            }
            for item in report.findings
        ],
        "affected_nodes": list(report.affected_nodes),
        "ranked_fault_classes": _rank_findings(report.findings),
    }


def _multiagent_citations(
    result: dict[str, Any], observable_evidence: dict[str, str]
) -> tuple[int, int, list[str]]:
    valid = 0
    total = 0
    invalid: set[str] = set()
    evidence_rows = {item["evidence_id"]: item for item in result["evidence"]}
    for finding in result["diagnostics"]:
        for evidence_id in finding["evidence_ids"]:
            total += 1
            if evidence_id in evidence_rows and evidence_id in observable_evidence:
                if evidence_rows[evidence_id]["kind"] != "retrieved_document_chunk":
                    valid += 1
                else:
                    invalid.add(evidence_id)
            else:
                invalid.add(evidence_id)
    for hypothesis in result["hypotheses"]:
        for evidence_id in hypothesis["supporting_evidence_ids"]:
            total += 1
            row = evidence_rows.get(evidence_id)
            if (
                row is not None
                and row["kind"] != "retrieved_document_chunk"
                and evidence_id in observable_evidence
            ):
                valid += 1
            else:
                invalid.add(evidence_id)
        for evidence_id in hypothesis["contradicting_evidence_ids"]:
            total += 1
            row = evidence_rows.get(evidence_id)
            if (
                row is not None
                and row["kind"] != "retrieved_document_chunk"
                and evidence_id in observable_evidence
            ):
                valid += 1
            else:
                invalid.add(evidence_id)
        for evidence_id in hypothesis["context_evidence_ids"]:
            total += 1
            row = evidence_rows.get(evidence_id)
            if (
                row is not None
                and row["kind"] == "retrieved_document_chunk"
                and evidence_id not in observable_evidence
            ):
                valid += 1
            else:
                invalid.add(evidence_id)
    return valid, total, sorted(invalid)


def _ranked_causes(result: dict[str, Any]) -> list[str]:
    return [item["fault_class"] for item in result["hypotheses"]]


def _top_k_hit(expected: set[str], ranked: list[str], k: int) -> float:
    if not expected:
        return float(not ranked)
    return float(bool(expected.intersection(ranked[:k])))


def _rank_metrics(
    truths: list[set[str]], predictions: list[list[str]], *, k: int
) -> dict[str, float | int]:
    positive = [(truth, guess) for truth, guess in zip(truths, predictions, strict=True) if truth]
    all_decisions = [
        bool(truth.intersection(guess[:1])) if truth else not guess
        for truth, guess in zip(truths, predictions, strict=True)
    ]
    top1 = [
        float(bool(truth.intersection(guess[:1])))
        for truth, guess in positive
    ]
    topk = [_top_k_hit(truth, guess, k) for truth, guess in positive]
    reciprocal = []
    for truth, guess in positive:
        first = next(
            (rank for rank, candidate in enumerate(guess, start=1) if candidate in truth),
            None,
        )
        reciprocal.append(1 / first if first else 0.0)
    clean_indexes = [index for index, truth in enumerate(truths) if not truth]
    correct_abstentions = sum(not predictions[index] for index in clean_indexes)
    return {
        "positive_cases": len(positive),
        "top_1_accuracy_on_positive_cases": sum(top1) / len(top1) if top1 else 1.0,
        f"top_{k}_accuracy_on_positive_cases": sum(topk) / len(topk) if topk else 1.0,
        "mean_reciprocal_rank_on_positive_cases": (
            sum(reciprocal) / len(reciprocal) if reciprocal else 1.0
        ),
        "decision_accuracy_including_clean_cases": (
            sum(all_decisions) / len(all_decisions) if all_decisions else 1.0
        ),
        "clean_cases": len(clean_indexes),
        "correct_abstentions": correct_abstentions,
        "clean_case_abstention_rate": (
            correct_abstentions / len(clean_indexes) if clean_indexes else 1.0
        ),
    }


def _evidence_metric(valid: int, total: int, invalid_ids: set[str]) -> dict[str, Any]:
    return {
        "valid_references": valid,
        "total_references": total,
        "invalid_references": total - valid,
        "validity_rate": valid / total if total else 1.0,
        "invalid_evidence_ids": sorted(invalid_ids),
    }


def run_investigation_benchmark(
    benchmark_dir: str | Path,
    runbooks_dir: str | Path,
    *,
    top_k: int | None = None,
) -> dict[str, Any]:
    """Run baseline and multi-agent systems without exposing truth to runtime input."""
    root = Path(benchmark_dir).resolve()
    manifest = _read_object(_safe_child(root, "manifest.json", label="manifest"))
    if set(manifest) - {"version", "as_of", "cases", "top_k"}:
        raise ValueError("Investigation manifest contains unsupported fields")
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Manifest version must be a non-empty string")
    cutoff_value = top_k if top_k is not None else manifest.get("top_k", 3)
    if isinstance(cutoff_value, bool) or not isinstance(cutoff_value, int) or cutoff_value < 1:
        raise ValueError("top_k must be a positive integer")

    as_of = None
    as_of_value = manifest.get("as_of")
    if as_of_value is not None:
        if not isinstance(as_of_value, str):
            raise ValueError("Manifest as_of must be an ISO-8601 string or null")
        normalized = f"{as_of_value[:-1]}+00:00" if as_of_value.endswith("Z") else as_of_value
        try:
            as_of = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("Manifest as_of must be a valid ISO-8601 timestamp") from exc
        if as_of.tzinfo is None:
            raise ValueError("Manifest as_of must include a UTC offset")

    specs = manifest.get("cases")
    if not isinstance(specs, list) or not specs:
        raise ValueError("Manifest cases must be a non-empty array")
    corpus = MarkdownCorpus.from_directory(runbooks_dir)

    expected_classes: list[set[str]] = []
    baseline_predictions: list[list[str]] = []
    multiagent_predictions: list[list[str]] = []
    expected_codes: list[set[str]] = []
    baseline_codes: list[set[str]] = []
    multiagent_codes: list[set[str]] = []
    expected_affected: list[set[str]] = []
    baseline_affected: list[set[str]] = []
    multiagent_affected: list[set[str]] = []
    case_results: list[dict[str, Any]] = []
    truth_seen: set[str] = set()
    observable_evidence_total = 0
    valid_references = 0
    invalid_reference_ids: set[str] = set()

    for index, spec in enumerate(specs):
        if not isinstance(spec, dict) or set(spec) != {"case_id", "input", "truth"}:
            raise ValueError(f"manifest cases[{index}] has invalid fields")
        case_id = spec.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in truth_seen:
            raise ValueError(f"manifest cases[{index}] has an empty or duplicate case_id")
        truth_seen.add(case_id)
        input_path = _safe_child(root, spec.get("input"), label=f"{case_id}.input")
        truth_path = _safe_child(root, spec.get("truth"), label=f"{case_id}.truth")
        if input_path == truth_path:
            raise ValueError(f"Runtime input and evaluator truth must be separate for {case_id!r}")

        input_payload = _read_object(input_path)
        case: IncidentCase = incident_case_from_mapping(input_payload)
        if case.case_id != case_id:
            raise ValueError(f"Input case_id mismatch for {case_id!r}")

        started = perf_counter()
        baseline = analyze_case(case, as_of=as_of)
        baseline_seconds = perf_counter() - started
        baseline_dict = _baseline_report_to_dict(baseline)

        started = perf_counter()
        result = InvestigationOrchestrator(
            corpus=corpus,
            budget=AgentBudget(),
        ).run(case, as_of=as_of)
        multiagent_seconds = perf_counter() - started
        result_dict = result_to_dict(result)
        multiagent_ranked = _ranked_causes(result_dict)

        # Read evaluator-only labels only after both prediction paths have completed.
        truth = _read_object(truth_path)
        truth_classes, truth_codes_set, truth_nodes = _truth_payload(truth, case_id=case_id)
        baseline_ranked = baseline_dict["ranked_fault_classes"]

        expected_classes.append(truth_classes)
        baseline_predictions.append(baseline_ranked)
        multiagent_predictions.append(multiagent_ranked)
        expected_codes.append(truth_codes_set)
        baseline_codes.append({item["code"] for item in baseline_dict["diagnostics"]})
        multiagent_codes.append({item["code"] for item in result_dict["diagnostics"]})
        expected_affected.append(truth_nodes)
        baseline_affected.append(set(baseline_dict["affected_nodes"]))
        multiagent_affected.append(set(result_dict["affected_nodes"]))

        observable_kinds = {item.evidence_id: item.kind for item in case.evidence}
        valid_refs, total_refs, invalid_ids = _multiagent_citations(result_dict, observable_kinds)
        valid_references += valid_refs
        observable_evidence_total += total_refs
        invalid_reference_ids.update(invalid_ids)

        case_results.append(
            {
                "case_id": case_id,
                "expected_fault_classes": sorted(truth_classes),
                "baseline_ranked_fault_classes": baseline_ranked,
                "multiagent_ranked_fault_classes": multiagent_ranked,
                "baseline_top_k_hit": _top_k_hit(truth_classes, baseline_ranked, cutoff_value),
                "multiagent_top_k_hit": _top_k_hit(truth_classes, multiagent_ranked, cutoff_value),
                "baseline_finding_codes_exact_match": baseline_codes[-1] == truth_codes_set,
                "multiagent_finding_codes_exact_match": multiagent_codes[-1] == truth_codes_set,
                "expected_affected_nodes": sorted(truth_nodes),
                "baseline_affected_nodes": sorted(baseline_affected[-1]),
                "multiagent_affected_nodes": sorted(multiagent_affected[-1]),
                "baseline_seconds": round(baseline_seconds, 6),
                "multiagent_seconds": round(multiagent_seconds, 6),
                "hypothesis_count": len(result_dict["hypotheses"]),
                "abstained": not multiagent_ranked,
                "verification_issue_codes": sorted(
                    {issue["code"] for issue in result_dict["verification_issues"]}
                ),
            }
        )

    baseline_cause_metrics = _rank_metrics(
        expected_classes, baseline_predictions, k=cutoff_value
    )
    multiagent_cause_metrics = _rank_metrics(
        expected_classes, multiagent_predictions, k=cutoff_value
    )
    return {
        "benchmark_version": version,
        "runtime_mode": "offline_deterministic_multi_agent",
        "case_count": len(case_results),
        "root_cause": {
            "baseline": baseline_cause_metrics,
            "multiagent": multiagent_cause_metrics,
        },
        "finding_code_detection": {
            "baseline": measure_sets(expected_codes, baseline_codes).to_dict(),
            "multiagent": measure_sets(expected_codes, multiagent_codes).to_dict(),
        },
        "affected_node_detection": {
            "baseline": measure_sets(expected_affected, baseline_affected).to_dict(),
            "multiagent": measure_sets(expected_affected, multiagent_affected).to_dict(),
        },
        "multiagent_evidence_reference_integrity": _evidence_metric(
            valid_references, observable_evidence_total, invalid_reference_ids
        ),
        "cases": case_results,
        "limitations": [
            (
                "The baseline and multi-agent variants in this run are both deterministic "
                "and offline; no language model is evaluated."
            ),
            (
                "The synthetic cases are controlled fixtures, not a representative dataset "
                "of production incidents."
            ),
            (
                "Fault-class top-k measures whether a labeled fault class appears among "
                "proposed candidates; it is not proof of causal attribution."
            ),
            "Evidence reference integrity checks source/type resolution, not semantic entailment.",
            "Wall-clock timings are observational and vary between runs.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Evaluate deterministic and multi-agent incident analysis on a versioned benchmark."""
    parser = argparse.ArgumentParser(
        prog="pipeline-rca-evaluate-investigation",
        description="Compare deterministic and multi-agent pipeline investigation baselines.",
    )
    parser.add_argument("--benchmark-dir", type=Path, default=Path("data/benchmark/v1"))
    parser.add_argument("--runbooks-dir", type=Path, default=Path("data/runbooks"))
    parser.add_argument("--top-k", type=int, help="override top-k cause metric cutoff")
    parser.add_argument("--output", type=Path, help="optional JSON report output path")
    args = parser.parse_args(argv)
    try:
        report = run_investigation_benchmark(
            args.benchmark_dir, args.runbooks_dir, top_k=args.top_k
        )
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (OSError, ValueError) as exc:
        print(f"pipeline-rca-evaluate-investigation: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
