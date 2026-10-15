"""Command-line interface for deterministic incident analysis."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline_rca.investigation import analyze_case
from pipeline_rca.models import InvestigationReport
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


def report_to_dict(report: InvestigationReport) -> dict[str, Any]:
    """Convert a report to a stable JSON-compatible structure."""
    return {
        "case_id": report.case_id,
        "status": report.status,
        "affected_nodes": list(report.affected_nodes),
        "findings": [
            {
                "code": finding.code,
                "fault_class": finding.fault_class.value,
                "severity": finding.severity.value,
                "summary": finding.summary,
                "evidence_ids": list(finding.evidence_ids),
                "observed": finding.observed,
                "expected": finding.expected,
            }
            for finding in report.findings
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Run an incident case from JSON and emit a machine-readable report."""
    parser = argparse.ArgumentParser(
        prog="pipeline-rca",
        description="Run deterministic, evidence-linked diagnostics for a pipeline incident.",
    )
    parser.add_argument("case", type=Path, help="path to observable incident-case JSON")
    parser.add_argument(
        "--as-of",
        type=_parse_as_of,
        help="explicit timezone-aware ISO-8601 time for reproducible freshness checks",
    )
    args = parser.parse_args(argv)

    try:
        raw_text = args.case.read_text(encoding="utf-8")
        payload = json.loads(raw_text)
        if not isinstance(payload, dict):
            raise ValueError("incident case JSON must be an object")
        case = incident_case_from_mapping(payload)
        report = analyze_case(case, as_of=args.as_of)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"pipeline-rca: error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report_to_dict(report), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
