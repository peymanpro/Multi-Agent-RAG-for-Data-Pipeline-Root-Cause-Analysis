"""Strict JSON boundary for observable incident cases."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pipeline_rca.models import (
    DatasetObservation,
    EvidenceRecord,
    IncidentCase,
    LineageEdge,
    SchemaSnapshot,
    TaskObservation,
    TaskStatus,
)

_FORBIDDEN_TRUTH_KEYS = frozenset(
    {"ground_truth", "hidden_truth", "expected_fault", "expected_root_cause", "label"}
)


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _array(value: object, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")
    return value


def _required_string(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_string(row: Mapping[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value


def _optional_integer(
    row: Mapping[str, Any], key: str, *, default: int | None = None
) -> int | None:
    value = row.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer or null")
    return value


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    items = _array(value, name)
    if any(not isinstance(item, str) for item in items):
        raise ValueError(f"{name} must contain only strings")
    return tuple(items)


def _reject_unknown_keys(row: Mapping[str, Any], allowed: set[str], name: str) -> None:
    forbidden = sorted(_FORBIDDEN_TRUTH_KEYS.intersection(row))
    if forbidden:
        raise ValueError(
            f"{name} contains evaluator-only field(s): {', '.join(forbidden)}"
        )
    unknown = sorted(set(row) - allowed)
    if unknown:
        raise ValueError(f"{name} contains unsupported field(s): {', '.join(unknown)}")


def incident_case_from_mapping(payload: Mapping[str, Any]) -> IncidentCase:
    """Validate JSON-like data and build the observable case contract.

    Unknown fields are rejected deliberately. In particular, evaluator labels must not
    leak into runtime incident input.
    """
    top_level = {
        "case_id",
        "question",
        "datasets",
        "schemas",
        "tasks",
        "lineage",
        "evidence",
    }
    _reject_unknown_keys(payload, top_level, "case")

    datasets: list[DatasetObservation] = []
    for index, raw in enumerate(_array(payload.get("datasets", []), "datasets")):
        row = _mapping(raw, f"datasets[{index}]")
        _reject_unknown_keys(
            row,
            {
                "dataset",
                "row_count",
                "expected_row_count",
                "duplicate_key_count",
                "latest_event_time",
                "freshness_threshold_seconds",
                "null_count_by_column",
                "evidence_id",
            },
            f"datasets[{index}]",
        )
        nulls_raw = _mapping(row.get("null_count_by_column", {}), "null_count_by_column")
        nulls: dict[str, int] = {}
        for column, count in nulls_raw.items():
            if isinstance(count, bool) or not isinstance(count, int):
                raise ValueError(f"null_count_by_column[{column!r}] must be an integer")
            nulls[column] = count
        datasets.append(
            DatasetObservation(
                dataset=_required_string(row, "dataset"),
                row_count=_optional_integer(row, "row_count"),
                expected_row_count=_optional_integer(row, "expected_row_count"),
                duplicate_key_count=_optional_integer(
                    row, "duplicate_key_count", default=0
                )
                or 0,
                latest_event_time=_optional_string(row, "latest_event_time"),
                freshness_threshold_seconds=_optional_integer(
                    row, "freshness_threshold_seconds"
                ),
                null_count_by_column=nulls,
                evidence_id=_optional_string(row, "evidence_id"),
            )
        )

    schemas: list[SchemaSnapshot] = []
    for index, raw in enumerate(_array(payload.get("schemas", []), "schemas")):
        row = _mapping(raw, f"schemas[{index}]")
        _reject_unknown_keys(
            row,
            {"dataset", "columns", "required_columns", "schema_version", "evidence_id"},
            f"schemas[{index}]",
        )
        schemas.append(
            SchemaSnapshot(
                dataset=_required_string(row, "dataset"),
                columns=_string_tuple(row.get("columns", []), "columns"),
                required_columns=_string_tuple(
                    row.get("required_columns", []), "required_columns"
                ),
                schema_version=_optional_string(row, "schema_version"),
                evidence_id=_optional_string(row, "evidence_id"),
            )
        )

    tasks: list[TaskObservation] = []
    for index, raw in enumerate(_array(payload.get("tasks", []), "tasks")):
        row = _mapping(raw, f"tasks[{index}]")
        _reject_unknown_keys(
            row,
            {"task_id", "status", "run_id", "started_at", "finished_at", "message", "evidence_id"},
            f"tasks[{index}]",
        )
        status_value = _required_string(row, "status")
        try:
            status = TaskStatus(status_value)
        except ValueError as exc:
            allowed = ", ".join(status.value for status in TaskStatus)
            raise ValueError(
                f"Invalid task status {status_value!r}; expected one of: {allowed}"
            ) from exc
        tasks.append(
            TaskObservation(
                task_id=_required_string(row, "task_id"),
                status=status,
                run_id=_optional_string(row, "run_id"),
                started_at=_optional_string(row, "started_at"),
                finished_at=_optional_string(row, "finished_at"),
                message=_optional_string(row, "message"),
                evidence_id=_optional_string(row, "evidence_id"),
            )
        )

    lineage: list[LineageEdge] = []
    for index, raw in enumerate(_array(payload.get("lineage", []), "lineage")):
        row = _mapping(raw, f"lineage[{index}]")
        _reject_unknown_keys(
            row, {"upstream", "downstream", "evidence_id"}, f"lineage[{index}]"
        )
        lineage.append(
            LineageEdge(
                upstream=_required_string(row, "upstream"),
                downstream=_required_string(row, "downstream"),
                evidence_id=_optional_string(row, "evidence_id"),
            )
        )

    evidence: list[EvidenceRecord] = []
    for index, raw in enumerate(_array(payload.get("evidence", []), "evidence")):
        row = _mapping(raw, f"evidence[{index}]")
        _reject_unknown_keys(
            row,
            {"evidence_id", "source", "locator", "summary", "kind", "observed_at"},
            f"evidence[{index}]",
        )
        evidence.append(
            EvidenceRecord(
                evidence_id=_required_string(row, "evidence_id"),
                source=_required_string(row, "source"),
                locator=_required_string(row, "locator"),
                summary=_required_string(row, "summary"),
                kind=_required_string(row, "kind"),
                observed_at=_optional_string(row, "observed_at"),
            )
        )

    return IncidentCase(
        case_id=_required_string(payload, "case_id"),
        question=_required_string(payload, "question"),
        datasets=tuple(datasets),
        schemas=tuple(schemas),
        tasks=tuple(tasks),
        lineage=tuple(lineage),
        evidence=tuple(evidence),
    )
