import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline_rca.api.app import create_app

ROOT = Path(__file__).resolve().parents[2]
RUNBOOKS = ROOT / "data" / "runbooks"
CASE_FILE = ROOT / "examples" / "cases" / "schema-drift.json"


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(create_app(runbooks_dir=RUNBOOKS)) as test_client:
        yield test_client


def test_liveness_is_independent_of_retrieval_readiness(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_loaded_runbook_counts(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["runbook_document_count"] == 5
    assert response.json()["runbook_chunk_count"] >= 5


def test_investigation_endpoint_returns_cited_offline_report(client: TestClient) -> None:
    case = json.loads(CASE_FILE.read_text(encoding="utf-8"))

    response = client.post("/v1/investigations", json={"case": case})

    assert response.status_code == 200
    report = response.json()
    assert report["case_id"] == "schema-drift-001"
    assert report["model_assisted"] is False
    assert report["model_calls"] == 0
    assert report["diagnostics"]
    assert report["hypotheses"]
    assert report["evidence"]
    assert report["trace"]
    available_ids = {item["evidence_id"] for item in report["evidence"]}
    for hypothesis in report["hypotheses"]:
        assert set(hypothesis["supporting_evidence_ids"]) <= available_ids


def test_api_rejects_hidden_benchmark_truth(client: TestClient) -> None:
    case = json.loads(CASE_FILE.read_text(encoding="utf-8"))
    case["ground_truth"] = {"expected_fault_classes": ["schema_drift"]}

    response = client.post("/v1/investigations", json={"case": case})

    assert response.status_code == 422
    assert "evaluator-only" in response.json()["detail"]


def test_api_rejects_naive_as_of_timestamp(client: TestClient) -> None:
    case = json.loads(CASE_FILE.read_text(encoding="utf-8"))

    response = client.post(
        "/v1/investigations",
        json={"case": case, "as_of": "2026-10-15T10:05:00"},
    )

    assert response.status_code == 422
    assert "explicit UTC offset" in response.json()["detail"]


def test_api_rejects_unconfigured_model_controls(client: TestClient) -> None:
    case = json.loads(CASE_FILE.read_text(encoding="utf-8"))

    response = client.post(
        "/v1/investigations",
        json={"case": case, "with_model": True},
    )

    assert response.status_code == 422


def test_api_bounds_oversized_case_payload(client: TestClient) -> None:
    response = client.post(
        "/v1/investigations",
        json={"case": {"case_id": "large", "question": "x" * 256_001}},
    )

    assert response.status_code == 413


def test_readiness_degrades_safely_when_runbooks_are_missing(tmp_path: Path) -> None:
    test_client = TestClient(create_app(runbooks_dir=tmp_path / "missing"))
    try:
        response = test_client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["retrieval_available"] is False

        case = json.loads(CASE_FILE.read_text(encoding="utf-8"))
        diagnosis = test_client.post(
            "/v1/investigations",
            json={"case": case, "use_runbooks": False},
        )
        assert diagnosis.status_code == 200
        assert diagnosis.json()["case_id"] == "schema-drift-001"
    finally:
        test_client.close()
