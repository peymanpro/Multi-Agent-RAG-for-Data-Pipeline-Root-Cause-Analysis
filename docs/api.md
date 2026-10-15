# Read-only Investigation API

## Scope

The optional HTTP layer exposes the existing bounded investigation runtime. It is intentionally read-only and does not expose arbitrary file paths, SQL execution, production credentials, destructive remediation, or hosted-model controls. Requests cannot turn on model calls through the API schema.

The API uses the same strict observable incident contract as the CLI. Evaluator-only fields such as `ground_truth`, `expected_root_cause`, and `label` are rejected.

## Run locally

Install the API and development extras from the repository root:

```bash
python -m pip install -e ".[api,dev]"
uvicorn pipeline_rca.api.app:app --host 127.0.0.1 --port 8000
```

The default runbook path is `data/runbooks`. Set `RCA_RUNBOOKS_DIR` to a readable local Markdown directory to override it. For authenticated local testing, set `RCA_API_AUTH_TOKEN` to a randomly generated token of at least 32 characters before starting the server. Interactive OpenAPI docs are available at `http://127.0.0.1:8000/docs`.

## Run with Docker Compose

```bash
docker compose up --build
```

Compose binds the service to `127.0.0.1:8000`, runs as a non-root user, drops Linux capabilities, uses a read-only container filesystem, and provides a bounded writable temporary filesystem. To require a Bearer token in the container, export `RCA_API_AUTH_TOKEN` in the host shell before starting Compose. This configuration is intended for local evaluation, not an internet-facing deployment.

## Endpoints

### `GET /health/live`

Reports whether the API process is responding. This endpoint does not depend on a valid runbook corpus.

### `GET /health/ready`

Reports whether the Markdown corpus is available. A missing or empty corpus yields HTTP 503 and a stable diagnostic reason. Diagnostic-only investigations remain available when the request explicitly sets `use_runbooks=false`.

### `POST /v1/investigations`

The request envelope contains an observable incident case, an optional timezone-aware evaluation timestamp, and an optional switch to disable runbook retrieval.

Example:

```json
{
  "case": {
    "case_id": "schema-drift-demo",
    "question": "Why is customer_id missing from the downstream dataset?",
    "schemas": [
      {
        "dataset": "staging.orders",
        "columns": ["order_id", "customer_ref", "amount"],
        "required_columns": ["order_id", "customer_id", "amount"],
        "schema_version": "source-v2",
        "evidence_id": "ev-schema-1"
      }
    ],
    "evidence": [
      {
        "evidence_id": "ev-schema-1",
        "source": "schema-registry",
        "locator": "staging.orders/source-v2",
        "summary": "The source has customer_ref; the downstream contract requires customer_id.",
        "kind": "schema_snapshot",
        "observed_at": "2026-10-15T10:00:00Z"
      }
    ]
  },
  "as_of": "2026-10-15T10:05:00Z",
  "use_runbooks": true
}
```

The response includes deterministic diagnostic findings, ranked hypotheses, evidence records, verification issues, and a bounded agent trace. Hypothesis confidence is explicitly marked as uncalibrated; a valid citation identifier is not proof of semantic entailment.

Common responses:

- `200`: the investigation completed or returned a partial/insufficient-evidence report.
- `401`: a configured Bearer token was absent or invalid. Authentication is disabled when `RCA_API_AUTH_TOKEN` is unset; health endpoints remain public for probes.
- `413`: the serialized case payload exceeds the application limit.
- `422`: request schema or incident contract validation failed.
- `503`: runbook retrieval was requested but its corpus is unavailable.

## Operational and security boundaries

- No model provider is instantiated by the HTTP API; model calls remain opt-in through the separate CLI.
- The request schema forbids unknown top-level request fields and strict incident parsing rejects hidden evaluator labels.
- The ASGI boundary rejects investigation HTTP bodies larger than 300,000 bytes before JSON parsing, including streamed bodies without a Content-Length header.
- After parsing, the serialized observable case is separately limited to 256,000 Unicode characters.
- When configured, `RCA_API_AUTH_TOKEN` protects `POST /v1/investigations` using a Bearer header and constant-time comparison. Tokens shorter than 32 characters or with surrounding whitespace are rejected at startup. Health endpoints remain public.
- This is a single shared token, not per-user authentication, tenant isolation, or role-based authorization. For shared/untrusted deployments, use an identity-aware gateway or implement a reviewed identity/authorization layer; rotate secrets and use TLS.
- The service does not mutate source datasets or run arbitrary SQL.
- The included Compose configuration is local-only. Bearer authentication is optional and can be enabled through `RCA_API_AUTH_TOKEN`, but user-level authorization, rate limiting, and TLS are not implemented. Do not expose the service directly to untrusted networks. Put it behind an authenticated gateway and apply deployment-specific resource limits before any shared deployment.
- Readiness is a dependency signal, not a security control or production-availability guarantee.
