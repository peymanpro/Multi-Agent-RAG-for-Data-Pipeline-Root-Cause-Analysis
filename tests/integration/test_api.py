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
    assert report["case_id"] == "example-schema-drift-001"
    assert report["model_assisted"] is False
    assert report["model_calls"] == 0
    assert report["diagnostics"]
    assert report["hypotheses"]
    assert report["evidence"]
    assert report["trace"]
    available_ids = {item["evidence_id"] for item in report["evidence"]}
    for hypothesis in report["hypotheses"]:
        assert set(hypothesis["supporting_evidence_ids"]) <= available_ids



def test_bearer_auth_protects_investigation_but_keeps_health_probes_public() -> None:
    token = "pipeline-rca-test-token-" + ("x" * 32)
    with TestClient(create_app(runbooks_dir=RUNBOOKS, auth_token=token)) as protected_client:
        assert protected_client.get("/health/live").status_code == 200
        assert protected_client.get("/health/ready").status_code == 200

        missing = protected_client.post(
            "/v1/investigations",
            content=b"{",
            headers={"content-type": "application/json"},
        )
        invalid = protected_client.post(
            "/v1/investigations",
            json={"case": json.loads(CASE_FILE.read_text(encoding="utf-8"))},
            headers={"Authorization": "Bearer wrong-token"},
        )
        valid = protected_client.post(
            "/v1/investigations",
            json={"case": json.loads(CASE_FILE.read_text(encoding="utf-8"))},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert missing.status_code == 401
    assert missing.json()["detail"] == "valid Bearer authentication is required"
    assert missing.headers["www-authenticate"] == "Bearer"
    assert invalid.status_code == 401
    assert token not in missing.text
    assert valid.status_code == 200
    assert valid.json()["case_id"] == "example-schema-drift-001"


def test_user_scopes_allow_or_deny_investigation_per_subject() -> None:
    investigator_token = "investigator-token-" + ("i" * 32)
    reader_token = "reader-token-" + ("r" * 32)
    users = json.dumps(
        [
            {
                "subject": "pipeline-operator",
                "token": investigator_token,
                "scopes": ["investigations:run"],
            },
            {
                "subject": "telemetry-reader",
                "token": reader_token,
                "scopes": ["telemetry:read"],
            },
        ]
    )
    case = json.loads(CASE_FILE.read_text(encoding="utf-8"))

    with TestClient(create_app(runbooks_dir=RUNBOOKS, users_json=users)) as scoped_client:
        permitted = scoped_client.post(
            "/v1/investigations",
            json={"case": case},
            headers={"Authorization": f"Bearer {investigator_token}", "X-Request-ID": "scope-test-1"},
        )
        denied = scoped_client.post(
            "/v1/investigations",
            json={"case": case},
            headers={"Authorization": f"Bearer {reader_token}"},
        )

    assert permitted.status_code == 200
    assert permitted.headers["x-request-id"] == "scope-test-1"
    assert denied.status_code == 403
    assert denied.json()["detail"] == "the authenticated subject lacks investigations:run"


def test_production_mode_fails_closed_without_identity_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RCA_DEPLOYMENT_MODE", "production")
    monkeypatch.delenv("RCA_API_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("RCA_API_USERS_JSON", raising=False)

    with pytest.raises(ValueError, match="authentication is required"):
        create_app(runbooks_dir=RUNBOOKS)


@pytest.mark.parametrize(
    ("token", "message"),
    [
        ("short", "at least 32 characters"),
        (" " + ("x" * 40), "surrounding whitespace"),
    ],
)
def test_bearer_auth_rejects_weak_or_malformed_tokens(token: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        create_app(runbooks_dir=RUNBOOKS, auth_token=token)


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
    errors = response.json()["detail"]
    assert any("explicit UTC offset" in error["msg"] for error in errors)


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


def test_api_rejects_oversized_http_body_before_json_parsing(client: TestClient) -> None:
    response = client.post(
        "/v1/investigations",
        content=b"x" * 300_001,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert "request body exceeds 300000 bytes" in response.json()["detail"]


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
        assert diagnosis.json()["case_id"] == "example-schema-drift-001"
    finally:
        test_client.close()
