"""Leakage-aware runner for the deterministic diagnostic baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

from pipeline_rca.investigation import analyze_case
from pipeline_rca.models import FaultClass, IncidentCase, InvestigationReport
from pipeline_rca.evaluation.metrics import SetMetrics, measure_sets
from pipeline_rca.serialization import incident_case_from_mapping


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


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


def _validate_truth(
    truth: dict[str, Any], *, case_id: str
) -> tuple[set[str], set[str], set[str]]:
    allowed = {
        "case_id",
        "expected_fault_classes",
        "expected_finding_codes",
        "expected_affected_nodes",
    }
    unknown = sorted(set(truth) - allowed)
    if unknown:
        raise ValueError(
            f"Evaluator truth for {case_id!r} has unsupported fields: {', '.join(unknown)}"
        )
    if truth.get("case_id") != case_id:
        raise ValueError(f"Evaluator truth case_id does not match manifest case {case_id!r}")

    fault_classes = _string_set(
        truth.get("expected_fault_classes"), label=f"{case_id}.expected_fault_classes"
    )
    valid_fault_classes = {fault.value for fault in FaultClass}
    invalid = sorted(fault_classes - valid_fault_classes)
    if invalid:
        raise ValueError(f"Unknown fault classes for {case_id!r}: {', '.join(invalid)}")

    finding_codes = _string_set(
        truth.get("expected_finding_codes"), label=f"{case_id}.expected_finding_codes"
    )
    affected_nodes = _string_set(
        truth.get("expected_affected_nodes"), label=f"{case_id}.expected_affected_nodes"
    )
    return fault_classes, finding_codes, affected_nodes


def _report_findings(report: InvestigationReport) -> tuple[set[str], set[str]]:
    return (
        {finding.fault_class.value for finding in report.findings},
        {finding.code for finding in report.findings},
    )


def _set_metrics_to_dict(metrics: SetMetrics) -> dict[str, int | float]:
    return metrics.to_dict()


def run_benchmark(root: Path) -> dict[str, Any]:
    """Run all cases in a benchmark directory and evaluate after each prediction.

    Runtime case input is parsed and analyzed before the corresponding truth file is
    opened. The evaluator contract is never added to IncidentCase or passed to diagnose().
    """
    root_resolved = root.resolve()
    manifest_path = _safe_child(root_resolved, "manifest.json", label="manifest")
    manifest = _read_object(manifest_path)
    unknown = sorted(set(manifest) - {"version", "as_of", "cases"})
    if unknown:
        raise ValueError(f"Manifest contains unsupported field(s): {', '.join(unknown)}")

    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Manifest version must be a non-empty string")

    as_of_value = manifest.get("as_of")
    as_of = None
    if as_of_value is not None:
        if not isinstance(as_of_value, str):
            raise ValueError("Manifest as_of must be an ISO-8601 string or null")
        normalized = (
            f"{as_of_value[:-1]}+00:00" if as_of_value.endswith("Z") else as_of_value
        )
        from datetime import datetime

        try:
            as_of = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"Invalid manifest as_of timestamp: {as_of_value!r}") from exc
        if as_of.tzinfo is None:
            raise ValueError("Manifest as_of timestamp must include a UTC offset")

    case_specs = manifest.get("cases")
    if not isinstance(case_specs, list) or not case_specs:
        raise ValueError("Manifest cases must be a non-empty array")

    seen_ids: set[str] = set()
    expected_faults: list[set[str]] = []
    predicted_faults: list[set[str]] = []
    expected_codes: list[set[str]] = []
    predicted_codes: list[set[str]] = []
    expected_affected: list[set[str]] = []
    predicted_affected: list[set[str]] = []
    case_results: list[dict[str, Any]] = []
    invalid_evidence_ids: set[str] = set()
    evidence_reference_count = 0
    valid_evidence_reference_count = 0

    for index, raw_spec in enumerate(case_specs):
        if not isinstance(raw_spec, dict):
            raise ValueError(f"manifest cases[{index}] must be an object")
        case_id = raw_spec.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"manifest cases[{index}].case_id must be a non-empty string")
        if case_id in seen_ids:
            raise ValueError(f"Duplicate benchmark case_id: {case_id}")
        seen_ids.add(case_id)

        input_path = _safe_child(
            root_resolved, raw_spec.get("input"), label=f"{case_id}.input"
        )
        truth_path = _safe_child(
            root_resolved, raw_spec.get("truth"), label=f"{case_id}.truth"
        )
        if input_path == truth_path:
            raise ValueError(f"Runtime input and evaluator truth must be separate for {case_id!r}")

        input_payload = _read_object(input_path)
        case: IncidentCase = incident_case_from_mapping(input_payload)
        if case.case_id != case_id:
            raise ValueError(
                f"Input case_id {case.case_id!r} does not match manifest {case_id!r}"
            )

        started = perf_counter()
        report = analyze_case(case, as_of=as_of)
        elapsed_seconds = perf_counter() - started

        # Ground truth is read only after the prediction has been produced.
        truth = _read_object(truth_path)
        expected_class_set, expected_code_set, expected_node_set = _validate_truth(
            truth, case_id=case_id
        )
        predicted_class_set, predicted_code_set = _report_findings(report)
        predicted_node_set = set(report.affected_nodes)

        allowed_evidence_ids = {item.evidence_id for item in case.evidence}
        cited_evidence_ids = [
            evidence_id
            for finding in report.findings
            for evidence_id in finding.evidence_ids
        ]
        invalid_for_case = sorted(
            {evidence_id for evidence_id in cited_evidence_ids if evidence_id not in allowed_evidence_ids}
        )
        evidence_reference_count += len(cited_evidence_ids)
        valid_evidence_reference_count += len(cited_evidence_ids) - sum(
            cited_evidence_ids.count(evidence_id) for evidence_id in invalid_for_case
        )
        invalid_evidence_ids.update(invalid_for_case)

        expected_faults.append(expected_class_set)
        predicted_faults.append(predicted_class_set)
        expected_codes.append(expected_code_set)
        predicted_codes.append(predicted_code_set)
        expected_affected.append(expected_node_set)
        predicted_affected.append(predicted_node_set)

        case_results.append(
            {
                "case_id": case_id,
                "status": report.status,
                "elapsed_seconds": round(elapsed_seconds, 6),
                "expected_fault_classes": sorted(expected_class_set),
                "predicted_fault_classes": sorted(predicted_class_set),
                "fault_classes_exact_match": expected_class_set == predicted_class_set,
                "expected_finding_codes": sorted(expected_code_set),
                "predicted_finding_codes": sorted(predicted_code_set),
                "finding_codes_exact_match": expected_code_set == predicted_code_set,
                "expected_affected_nodes": sorted(expected_node_set),
                "predicted_affected_nodes": sorted(predicted_node_set),
                "affected_nodes_exact_match": expected_node_set == predicted_node_set,
                "invalid_evidence_ids": invalid_for_case,
                "finding_count": len(report.findings),
            }
        )

    reference_validity = (
        valid_evidence_reference_count / evidence_reference_count
        if evidence_reference_count
        else 1.0
    )
    return {
        "benchmark_version": version,
        "system": "deterministic_diagnostics_baseline",
        "case_count": len(case_results),
        "metrics": {
            "fault_class_detection": _set_metrics_to_dict(
                measure_sets(expected_faults, predicted_faults)
            ),
            "finding_code_detection": _set_metrics_to_dict(
                measure_sets(expected_codes, predicted_codes)
            ),
            "affected_node_detection": _set_metrics_to_dict(
                measure_sets(expected_affected, predicted_affected)
            ),
            "evidence_reference_validity": {
                "references": evidence_reference_count,
                "valid_references": valid_evidence_reference_count,
                "invalid_references": evidence_reference_count - valid_evidence_reference_count,
                "validity_rate": reference_validity,
                "invalid_evidence_ids": sorted(invalid_evidence_ids),
            },
        },
        "cases": case_results,
        "limitations": [
            "This first benchmark measures deterministic diagnostic detection, not LLM root-cause accuracy.",
            "Synthetic cases are controlled fixtures and do not establish production performance.",
            "Runtime timing is observational and may vary between runs.",
            "Evaluator truth files are separate from runtime input but are public repository files; this is separation by interface, not secrecy.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark from a directory containing manifest.json."""
    parser = argparse.ArgumentParser(
        prog="pipeline-rca-benchmark",
        description="Evaluate deterministic pipeline diagnostics on a versioned benchmark.",
    )
    parser.add_argument(
        "benchmark_dir",
        nargs="?",
        type=Path,
        default=Path("data/benchmark/v1"),
        help="directory containing manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional path for the machine-readable JSON report",
    )
    args = parser.parse_args(argv)

    try:
        report = run_benchmark(args.benchmark_dir)
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (OSError, ValueError) as exc:
        print(f"pipeline-rca-benchmark: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
