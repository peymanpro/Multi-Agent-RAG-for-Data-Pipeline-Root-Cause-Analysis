"""Contract tests for the read-only Airflow REST adapter."""

from __future__ import annotations

from typing import Any

from pipeline_rca.connectors.airflow import AirflowRestConnector
from pipeline_rca.connectors.base import ConnectorError


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_json(self, path: str) -> dict[str, Any]:
        self.calls.append(path)
        if path.endswith("/dagRuns/run-1"):
            return {"state": "failed", "start_date": "2026-10-15T00:00:00Z"}
        if path.endswith("/tasks"):
            return {
                "tasks": [
                    {"task_id": "extract", "downstream_task_ids": ["transform"]},
                    {"task_id": "transform", "downstream_task_ids": []},
                ]
            }
        if path.endswith("/taskInstances?limit=1000"):
            return {
                "task_instances": [
                    {"task_id": "extract", "state": "success"},
                    {"task_id": "transform", "state": "upstream_failed"},
                ]
            }
        raise AssertionError(f"unexpected API path {path}")


def test_airflow_connector_maps_runs_tasks_and_dependencies() -> None:
    client = FakeClient()
    snapshot = AirflowRestConnector(client).read_dag_run("orders-dag", "run-1")

    assert len(client.calls) == 3
    assert all(path.startswith("api/v1/") for path in client.calls)
    assert {task.status.value for task in snapshot.tasks} == {"success", "failed"}
    assert len(snapshot.evidence) == 3
    assert len(snapshot.lineage) == 1
    assert snapshot.lineage[0].upstream == "airflow://orders-dag/extract"
    assert snapshot.lineage[0].downstream == "airflow://orders-dag/transform"
    case = snapshot.to_incident_case(
        case_id="airflow-case-1",
        question="Why did the orders pipeline fail?",
    )
    assert case.case_id == "airflow-case-1"
    assert case.evidence == snapshot.evidence


def test_airflow_connector_rejects_missing_identifiers() -> None:
    try:
        AirflowRestConnector(FakeClient()).read_dag_run("", "run-1")
    except ConnectorError as exc:
        assert "required" in str(exc)
    else:
        raise AssertionError("missing dag_id must be rejected")
