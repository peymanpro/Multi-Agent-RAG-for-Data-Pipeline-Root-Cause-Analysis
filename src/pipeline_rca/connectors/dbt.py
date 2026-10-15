"""Read-only adapter for dbt manifest.json and run_results.json artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline_rca.connectors.base import ConnectorError, make_evidence
from pipeline_rca.connectors.models import ConnectorSnapshot
from pipeline_rca.models import LineageEdge, SchemaSnapshot, TaskObservation, TaskStatus

_MAX_ARTIFACT_BYTES = 20_000_000
_STATUS_MAP = {
    "success": TaskStatus.SUCCESS,
    "pass": TaskStatus.SUCCESS,
    "error": TaskStatus.FAILED,
    "fail": TaskStatus.FAILED,
    "skipped": TaskStatus.SKIPPED,
    "runtime error": TaskStatus.FAILED,
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file():
            raise ConnectorError(f"required dbt artifact is missing: {path.name}")
        if path.stat().st_size > _MAX_ARTIFACT_BYTES:
            raise ConnectorError(f"dbt artifact exceeded {_MAX_ARTIFACT_BYTES} bytes: {path.name}")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ConnectorError(f"could not read dbt artifact {path.name}") from exc
    if not isinstance(value, dict):
        raise ConnectorError(f"dbt artifact {path.name} must contain a JSON object")
    return value


class DbtArtifactConnector:
    """Normalize read-only dbt artifacts without invoking dbt or executing SQL."""

    def __init__(self, artifacts_dir: str | Path, *, max_artifact_bytes: int = _MAX_ARTIFACT_BYTES):
        self.artifacts_dir = Path(artifacts_dir).resolve()
        if max_artifact_bytes < 1:
            raise ConnectorError("max_artifact_bytes must be positive")
        self.max_artifact_bytes = max_artifact_bytes

    def _read(self, name: str) -> dict[str, Any]:
        path = (self.artifacts_dir / name).resolve()
        if path.parent != self.artifacts_dir:
            raise ConnectorError("dbt artifact path escaped the configured directory")
        try:
            if not path.is_file():
                raise ConnectorError(f"required dbt artifact is missing: {name}")
            if path.stat().st_size > self.max_artifact_bytes:
                raise ConnectorError(f"dbt artifact exceeded the configured byte limit: {name}")
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ConnectorError(f"could not read dbt artifact {name}") from exc
        if not isinstance(value, dict):
            raise ConnectorError(f"dbt artifact {name} must contain a JSON object")
        return value

    def read(self) -> ConnectorSnapshot:
        """Load model metadata, run statuses and dependency edges from local artifacts."""
        manifest = self._read("manifest.json")
        run_results = self._read("run_results.json")
        nodes = manifest.get("nodes")
        results = run_results.get("results")
        if not isinstance(nodes, dict) or not isinstance(results, list):
            raise ConnectorError("dbt artifacts must include nodes and results collections")

        observed_at = datetime.now(UTC).isoformat()
        evidence = []
        schemas: list[SchemaSnapshot] = []
        lineage: list[LineageEdge] = []
        tasks: list[TaskObservation] = []
        manifest_evidence_ids: dict[str, str] = {}

        for unique_id, node in nodes.items():
            if not isinstance(unique_id, str) or not isinstance(node, dict):
                continue
            if node.get("resource_type") not in {"model", "seed", "snapshot"}:
                continue
            depends_on = node.get("depends_on", {})
            dependencies = depends_on.get("nodes", []) if isinstance(depends_on, dict) else []
            if not isinstance(dependencies, list):
                raise ConnectorError(f"dbt node {unique_id!r} has malformed dependencies")
            name = str(node.get("name", unique_id))[:160]
            relation = ".".join(
                str(part) for part in (node.get("database"), node.get("schema"), node.get("alias") or name)
                if part
            )
            locator = f"manifest.json#nodes/{unique_id}"
            row = make_evidence(
                source="dbt-artifact",
                locator=locator,
                summary=f"dbt {node.get('resource_type')} model metadata loaded for {name}.",
                kind="dbt_model",
                payload_for_id={
                    "unique_id": unique_id,
                    "resource_type": node.get("resource_type"),
                    "relation": relation,
                    "depends_on": dependencies,
                },
                observed_at=observed_at,
            )
            evidence.append(row)
            manifest_evidence_ids[unique_id] = row.evidence_id
            columns = node.get("columns", {})
            if isinstance(columns, dict):
                column_names = tuple(sorted(str(column) for column in columns))
                if column_names:
                    schemas.append(
                        SchemaSnapshot(
                            dataset=relation or unique_id,
                            columns=column_names,
                            evidence_id=row.evidence_id,
                        )
                    )
            for upstream in dependencies:
                if isinstance(upstream, str):
                    lineage.append(LineageEdge(upstream=f"dbt://{upstream}", downstream=f"dbt://{unique_id}"))

        for index, result in enumerate(results):
            if not isinstance(result, dict) or not isinstance(result.get("unique_id"), str):
                raise ConnectorError(f"dbt run_results.results[{index}] has no unique_id")
            unique_id = result["unique_id"]
            state = str(result.get("status", "unknown")).lower()
            status = _STATUS_MAP.get(state, TaskStatus.UNKNOWN)
            locator = f"run_results.json#results/{index}"
            row = make_evidence(
                source="dbt-artifact",
                locator=locator,
                summary=f"dbt node {unique_id[:180]} completed with status {state[:80]}.",
                kind="dbt_run_result",
                payload_for_id={
                    "unique_id": unique_id,
                    "status": state,
                    "execution_time": result.get("execution_time"),
                },
                observed_at=observed_at,
            )
            evidence.append(row)
            tasks.append(
                TaskObservation(
                    task_id=f"dbt://{unique_id}",
                    status=status,
                    finished_at=observed_at,
                    message=f"dbt status: {state[:80]}",
                    evidence_id=row.evidence_id or manifest_evidence_ids.get(unique_id),
                )
            )

        digest = hashlib.sha256(
            json.dumps(run_results.get("metadata", {}), sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return ConnectorSnapshot(
            source="dbt-artifact",
            observed_at=observed_at,
            evidence=tuple(evidence),
            tasks=tuple(tasks),
            lineage=tuple(sorted(lineage, key=lambda edge: (edge.upstream, edge.downstream))),
            schemas=tuple(schemas),
        )
