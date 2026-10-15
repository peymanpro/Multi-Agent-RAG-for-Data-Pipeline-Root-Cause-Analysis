"""Read-only OpenLineage JSON-lines event adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline_rca.connectors.base import ConnectorError, make_evidence
from pipeline_rca.connectors.models import ConnectorSnapshot
from pipeline_rca.models import EvidenceRecord, LineageEdge, SchemaSnapshot, TaskObservation, TaskStatus

_MAX_FILE_BYTES = 20_000_000
_MAX_EVENTS = 10_000
_STATE_MAP = {
    "COMPLETE": TaskStatus.SUCCESS,
    "FAIL": TaskStatus.FAILED,
    "ABORT": TaskStatus.FAILED,
    "START": TaskStatus.RUNNING,
    "RUNNING": TaskStatus.RUNNING,
}


def _dataset_name(value: object) -> str | None:
    if not isinstance(value, dict) or not isinstance(value.get("name"), str):
        return None
    namespace = value.get("namespace", "")
    if not isinstance(namespace, str):
        namespace = ""
    return f"{namespace}/{value['name']}" if namespace else value["name"]


class OpenLineageEventFileConnector:
    """Parse bounded OpenLineage events from a local JSON-lines export."""

    def __init__(self, path: str | Path, *, max_file_bytes: int = _MAX_FILE_BYTES):
        self.path = Path(path).resolve()
        if max_file_bytes < 1:
            raise ConnectorError("max_file_bytes must be positive")
        self.max_file_bytes = max_file_bytes

    def read(self) -> ConnectorSnapshot:
        """Normalize event/run states, dataset lineage, and output schema facets."""
        try:
            if not self.path.is_file():
                raise ConnectorError("OpenLineage event file does not exist")
            if self.path.stat().st_size > self.max_file_bytes:
                raise ConnectorError("OpenLineage event file exceeds the configured byte limit")
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise ConnectorError("could not read OpenLineage event file") from exc
        if len(lines) > _MAX_EVENTS:
            raise ConnectorError(f"OpenLineage event count exceeds {_MAX_EVENTS}")

        observed_at = datetime.now(UTC).isoformat()
        evidence: list[EvidenceRecord] = []
        tasks: list[TaskObservation] = []
        lineage: set[tuple[str, str]] = set()
        schemas: list[SchemaSnapshot] = []

        for index, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                event: Any = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ConnectorError(f"OpenLineage line {index + 1} is invalid JSON") from exc
            if not isinstance(event, dict):
                raise ConnectorError(f"OpenLineage line {index + 1} must be a JSON object")
            job = event.get("job", {})
            run = event.get("run", {})
            if not isinstance(job, dict) or not isinstance(run, dict):
                raise ConnectorError(f"OpenLineage line {index + 1} has malformed job/run fields")
            job_name = str(job.get("name", "unknown"))[:200]
            namespace = str(job.get("namespace", ""))[:200]
            run_id = str(run.get("runId", "unknown"))[:200]
            event_type = str(event.get("eventType", "OTHER")).upper()[:40]
            event_time = event.get("eventTime")
            event_time_string = event_time if isinstance(event_time, str) else None
            locator = f"events.jsonl#{index + 1}"
            row = make_evidence(
                source="openlineage-event",
                locator=locator,
                summary=f"OpenLineage {event_type} event for job {job_name} run {run_id}.",
                kind="lineage_event",
                payload_for_id={
                    "job": job_name,
                    "namespace": namespace,
                    "run_id": run_id,
                    "event_type": event_type,
                    "event_time": event_time_string,
                },
                observed_at=event_time_string or observed_at,
            )
            evidence.append(row)
            tasks.append(
                TaskObservation(
                    task_id=f"openlineage://{namespace}/{job_name}",
                    status=_STATE_MAP.get(event_type, TaskStatus.UNKNOWN),
                    run_id=run_id,
                    started_at=event_time_string if event_type == "START" else None,
                    finished_at=(
                        event_time_string if event_type in {"COMPLETE", "FAIL", "ABORT"} else None
                    ),
                    evidence_id=row.evidence_id,
                )
            )
            inputs = event.get("inputs", [])
            outputs = event.get("outputs", [])
            if not isinstance(inputs, list) or not isinstance(outputs, list):
                raise ConnectorError(f"OpenLineage line {index + 1} has invalid inputs/outputs")
            input_names = [name for item in inputs if (name := _dataset_name(item)) is not None]
            output_names = [name for item in outputs if (name := _dataset_name(item)) is not None]
            for upstream in input_names:
                for downstream in output_names:
                    lineage.add((f"dataset://{upstream}", f"dataset://{downstream}"))

            for output in outputs:
                if not isinstance(output, dict):
                    continue
                name = _dataset_name(output)
                facets = output.get("facets", {})
                schema = facets.get("schema", {}) if isinstance(facets, dict) else {}
                fields = schema.get("fields", []) if isinstance(schema, dict) else []
                if name and isinstance(fields, list):
                    columns = tuple(
                        sorted(field["name"] for field in fields
                               if isinstance(field, dict) and isinstance(field.get("name"), str))
                    )
                    if columns:
                        schemas.append(
                            SchemaSnapshot(dataset=name, columns=columns, evidence_id=row.evidence_id)
                        )

        return ConnectorSnapshot(
            source="openlineage-event",
            observed_at=observed_at,
            evidence=tuple(evidence),
            tasks=tuple(tasks),
            lineage=tuple(LineageEdge(upstream=a, downstream=b) for a, b in sorted(lineage)),
            schemas=tuple(schemas),
        )
