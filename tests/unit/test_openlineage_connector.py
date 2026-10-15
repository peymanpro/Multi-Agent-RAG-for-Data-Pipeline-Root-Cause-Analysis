"""Contract tests for OpenLineage JSON-lines exports."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline_rca.connectors.openlineage import OpenLineageEventFileConnector


def test_openlineage_events_yield_status_lineage_and_output_schema(tmp_path: Path) -> None:
    events = [
        {
            "eventType": "COMPLETE",
            "eventTime": "2026-10-15T10:00:00Z",
            "run": {"runId": "run-1"},
            "job": {"namespace": "airflow", "name": "build-orders"},
            "inputs": [{"namespace": "warehouse", "name": "raw.orders"}],
            "outputs": [
                {
                    "namespace": "warehouse",
                    "name": "analytics.orders",
                    "facets": {
                        "schema": {
                            "fields": [
                                {"name": "order_id", "type": "INT"},
                                {"name": "revenue", "type": "DECIMAL"},
                            ]
                        }
                    },
                }
            ],
        },
        {
            "eventType": "FAIL",
            "eventTime": "2026-10-15T10:02:00Z",
            "run": {"runId": "run-2"},
            "job": {"namespace": "airflow", "name": "validate-orders"},
            "inputs": [{"namespace": "warehouse", "name": "analytics.orders"}],
            "outputs": [],
        },
    ]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")

    snapshot = OpenLineageEventFileConnector(path).read()

    assert [task.status.value for task in snapshot.tasks] == ["success", "failed"]
    assert len(snapshot.lineage) == 1
    assert snapshot.lineage[0].upstream == "dataset://warehouse/raw.orders"
    assert snapshot.lineage[0].downstream == "dataset://warehouse/analytics.orders"
    assert snapshot.schemas[0].columns == ("order_id", "revenue")
    assert len(snapshot.evidence) == 2
    assert all("secret" not in record.summary for record in snapshot.evidence)


def test_openlineage_empty_event_file_is_a_valid_empty_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("", encoding="utf-8")

    assert OpenLineageEventFileConnector(path).read().evidence == ()
