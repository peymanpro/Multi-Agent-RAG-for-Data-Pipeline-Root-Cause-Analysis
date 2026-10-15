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

The default runbook path is `data/runbooks`. Set `RCA_RUNBOOKS_DIR` to a readable local Markdown directory to override it. Interactive OpenAPI docs are available at `http://127.0.0.1:8000/docs`.

### Per-user authentication and authorization

For local single-token compatibility, `RCA_API_AUTH_TOKEN` remains supported. For per-user access, configure `RCA_API_USERS_JSON` as a protected runtime secret:

```json
[
  {
    "subject": "pipeline-operator",
    "token": "replace-with-a-random-secret-at-least-32-characters",
    "scopes": ["investigations:run", "connectors:read"]
  },
  {
    "subject": "auditor",
    "token": "use-a-different-random-secret-at-least-32-characters",
    "scopes": ["telemetry:read"]
  }
]
```

Supported scope labels are `investigations:run`, `connectors:read`, and `telemetry:read`. The current HTTP surface exposes only `POST /v1/investigations`, which requires `investigations:run`; the other two labels are reserved for future separately reviewed API routes and do not expose connector or telemetry data endpoints in this release. The Airflow, dbt, and OpenLineage adapters are currently library-level, read-only connectors. Subjects must be unique; tokens must be unique and at least 32 characters. Unknown scopes, duplicate identities, or combining the legacy shared token with the per-user registry cause startup failure. Secrets should be injected by an orchestrator/secret manager and never committed to Git or copied into logs.

Set `RCA_DEPLOYMENT_MODE=production` (or `RCA_API_AUTH_REQUIRED=true`) to make the application fail at startup when no authentication credentials are configured. With credentials configured, health probes remain public, unauthenticated investigation requests receive 401, and authenticated users lacking `investigations:run` receive 403. This is static per-user API-token authorization, not a full OIDC/SSO integration; production identity lifecycle, revocation, and secret rotation remain operator responsibilities.

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
- `401`: a configured Bearer token was absent or invalid.
- `403`: the authenticated principal does not have the `investigations:run` scope.
- `503`: runbook retrieval was requested but its corpus is unavailable.
- `413`: the serialized case payload exceeds the application limit.
- `422`: request schema or incident contract validation failed.
- `503`: runbook retrieval was requested but its corpus is unavailable.

## Operational and security boundaries

- No model provider is instantiated by the HTTP API; model calls remain opt-in through the separate CLI.
- The request schema forbids unknown top-level request fields and strict incident parsing rejects hidden evaluator labels.
- The ASGI boundary rejects investigation HTTP bodies larger than 300,000 bytes before JSON parsing, including streamed bodies without a Content-Length header.
- After parsing, the serialized observable case is separately limited to 256,000 Unicode characters.
- `RCA_API_USERS_JSON` provides separate bearer tokens, subject identities, and explicit scopes. `RCA_API_AUTH_TOKEN` is retained only as a legacy single-subject compatibility mode.
- The application emits structured JSON-line request telemetry with a validated/generated `X-Request-ID`, method, path (without query), status, duration, outcome, and authenticated subject. It intentionally excludes headers, query strings, request/response bodies, and token values.
- The service does not mutate source datasets or run arbitrary SQL.
- The included Compose configuration is local-only. The API applies a process-local rate limiter in development; multi-worker production mode requires Redis-backed limiting and per-user API credentials. Static API tokens are not a replacement for OIDC/SSO identity lifecycle. See [distributed rate limiting](rate-limiting.md) before configuring multiple workers. Do not expose the service directly to untrusted networks.
- Readiness is a dependency signal, not a security control or production-availability guarantee.
