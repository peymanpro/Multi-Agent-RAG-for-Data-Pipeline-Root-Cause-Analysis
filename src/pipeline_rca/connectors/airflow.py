"""Read-only Apache Airflow REST API adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from pipeline_rca.connectors.base import ConnectorError, HttpJsonClient, JsonGetClient, make_evidence
from pipeline_rca.connectors.models import ConnectorSnapshot
from pipeline_rca.models import LineageEdge, TaskObservation, TaskStatus

_AIRFLOW_STATES = {
    "success": TaskStatus.SUCCESS,
    "failed": TaskStatus.FAILED,
    "upstream_failed": TaskStatus.FAILED,
    "running": TaskStatus.RUNNING,
    "queued": TaskStatus.RUNNING,
    "scheduled": TaskStatus.RUNNING,
    "skipped": TaskStatus.SKIPPED,
}


def _state(value: object) -> TaskStatus:
    return _AIRFLOW_STATES.get(str(value).lower(), TaskStatus.UNKNOWN)


class AirflowRestConnector:
    """Pull one Airflow DAG run and its task/dependency metadata using GET requests only."""

    def __init__(self, client: JsonGetClient) -> None:
        self._client = client

    @classmethod
    def from_config(
        cls,
        base_url: str,
        *,
        bearer_token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout_seconds: float = 8.0,
    ) -> AirflowRestConnector:
        """Build a connector from operator-supplied source settings."""
        return cls(
            HttpJsonClient(
                base_url,
                bearer_token=bearer_token,
                username=username,
                password=password,
                timeout_seconds=timeout_seconds,
            )
        )

    def read_dag_run(self, dag_id: str, run_id: str) -> ConnectorSnapshot:
        """Read a DAG run, task instances and declared task dependencies."""
        if not dag_id or not run_id:
            raise ConnectorError("dag_id and run_id are required")
        dag = quote(dag_id, safe="")
        run = quote(run_id, safe="")
        run_path = f"api/v1/dags/{dag}/dagRuns/{run}"
        run_data = self._client.get_json(run_path)
        task_data = self._client.get_json(f"api/v1/dags/{dag}/tasks")
        instances_data = self._client.get_json(f"{run_path}/taskInstances?limit=1000")

        task_specs = task_data.get("tasks")
        instances = instances_data.get("task_instances")
        if not isinstance(task_specs, list) or not isinstance(instances, list):
            raise ConnectorError("Airflow response omitted tasks or task_instances arrays")
        observed_at = datetime.now(UTC).isoformat()
        evidence = []
        observations: list[TaskObservation] = []
        lineage: list[LineageEdge] = []

        dag_state = run_data.get("state", "unknown")
        run_locator = f"dags/{dag_id}/dagRuns/{run_id}"
        run_evidence = make_evidence(
            source="airflow-rest",
            locator=run_locator,
            summary=f"Airflow DAG run state is {str(dag_state)[:80]}.",
            kind="task_run",
            payload_for_id={"dag_id": dag_id, "run_id": run_id, "state": dag_state},
            observed_at=observed_at,
        )
        evidence.append(run_evidence)
        observations.append(
            TaskObservation(
                task_id=f"{dag_id}::{run_id}",
                status=_state(dag_state),
                run_id=run_id,
                started_at=run_data.get("start_date")
                if isinstance(run_data.get("start_date"), str)
                else None,
                finished_at=run_data.get("end_date")
                if isinstance(run_data.get("end_date"), str)
                else None,
                evidence_id=run_evidence.evidence_id,
            )
        )

        for index, item in enumerate(instances):
            if not isinstance(item, dict) or not isinstance(item.get("task_id"), str):
                raise ConnectorError(f"Airflow task_instances[{index}] has no task_id")
            task_id = item["task_id"]
            state = item.get("state", "unknown")
            locator = f"{run_locator}/taskInstances/{task_id}"
            row_evidence = make_evidence(
                source="airflow-rest",
                locator=locator,
                summary=f"Airflow task {task_id[:120]} state is {str(state)[:80]}.",
                kind="task_instance",
                payload_for_id={
                    "dag_id": dag_id,
                    "run_id": run_id,
                    "task_id": task_id,
                    "state": state,
                },
                observed_at=observed_at,
            )
            evidence.append(row_evidence)
            observations.append(
                TaskObservation(
                    task_id=f"airflow://{dag_id}/{task_id}",
                    status=_state(state),
                    run_id=run_id,
                    started_at=item.get("start_date")
                    if isinstance(item.get("start_date"), str)
                    else None,
                    finished_at=item.get("end_date")
                    if isinstance(item.get("end_date"), str)
                    else None,
                    evidence_id=row_evidence.evidence_id,
                )
            )

        for index, spec in enumerate(task_specs):
            if not isinstance(spec, dict) or not isinstance(spec.get("task_id"), str):
                raise ConnectorError(f"Airflow tasks[{index}] has no task_id")
            task_id = spec["task_id"]
            downstream = spec.get("downstream_task_ids", [])
            if not isinstance(downstream, list) or any(
                not isinstance(name, str) for name in downstream
            ):
                raise ConnectorError(f"Airflow task {task_id!r} has invalid downstream_task_ids")
            for child in downstream:
                lineage.append(
                    LineageEdge(
                        upstream=f"airflow://{dag_id}/{task_id}",
                        downstream=f"airflow://{dag_id}/{child}",
                    )
                )

        return ConnectorSnapshot(
            source="airflow-rest",
            observed_at=observed_at,
            evidence=tuple(evidence),
            tasks=tuple(observations),
            lineage=tuple(sorted(lineage, key=lambda edge: (edge.upstream, edge.downstream))),
        )
