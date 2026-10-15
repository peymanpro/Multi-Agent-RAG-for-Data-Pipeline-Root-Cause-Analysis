"""Contract tests for read-only dbt artifact ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline_rca.connectors.base import ConnectorError
from pipeline_rca.connectors.dbt import DbtArtifactConnector


def test_dbt_artifacts_yield_task_state_schema_and_lineage(tmp_path: Path) -> None:
    manifest = {
        "nodes": {
            "model.demo.stg_orders": {
                "resource_type": "model",
                "name": "stg_orders",
                "database": "warehouse",
                "schema": "staging",
                "alias": "stg_orders",
                "columns": {"order_id": {}, "customer_id": {}},
                "depends_on": {"nodes": []},
            },
            "model.demo.fact_orders": {
                "resource_type": "model",
                "name": "fact_orders",
                "database": "warehouse",
                "schema": "analytics",
                "alias": "fact_orders",
                "columns": {"order_id": {}, "revenue": {}},
                "depends_on": {"nodes": ["model.demo.stg_orders"]},
            },
        }
    }
    results = {
        "metadata": {"dbt_version": "test"},
        "results": [
            {"unique_id": "model.demo.stg_orders", "status": "success", "execution_time": 0.1},
            {"unique_id": "model.demo.fact_orders", "status": "error", "execution_time": 0.2},
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "run_results.json").write_text(json.dumps(results), encoding="utf-8")

    snapshot = DbtArtifactConnector(tmp_path).read()

    assert len(snapshot.schemas) == 2
    assert snapshot.schemas[0].columns == ("customer_id", "order_id")
    assert [task.status.value for task in snapshot.tasks] == ["success", "failed"]
    assert len(snapshot.lineage) == 1
    assert snapshot.lineage[0].upstream == "dbt://model.demo.stg_orders"
    assert snapshot.lineage[0].downstream == "dbt://model.demo.fact_orders"
    assert all("dbt" in item.source for item in snapshot.evidence)


def test_dbt_connector_rejects_missing_or_malformed_artifacts(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("[]", encoding="utf-8")
    (tmp_path / "run_results.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ConnectorError, match="JSON object"):
        DbtArtifactConnector(tmp_path).read()


def test_dbt_connector_enforces_artifact_size_limit(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text('{"nodes":{}}', encoding="utf-8")
    (tmp_path / "run_results.json").write_text('{"results":[]}', encoding="utf-8")

    with pytest.raises(ConnectorError, match="byte limit"):
        DbtArtifactConnector(tmp_path, max_artifact_bytes=2).read()
