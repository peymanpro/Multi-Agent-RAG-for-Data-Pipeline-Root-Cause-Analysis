# Read-only Production Data Connectors

The connector layer normalizes operational source metadata into the repository's typed incident contracts. It is intentionally read-only: the adapters issue HTTP GET requests or read exported artifacts; they do not launch jobs, execute SQL, mutate source systems, or perform remediation.

## Supported sources

### Apache Airflow REST API

`AirflowRestConnector` reads one configured DAG run, its task instances, and declared task dependencies through the stable REST API. It maps task outcomes into `TaskObservation`, source-addressable `EvidenceRecord` entries, and task dependency edges.

```python
import os

from pipeline_rca.connectors.airflow import AirflowRestConnector

connector = AirflowRestConnector.from_config(
    os.environ["AIRFLOW_API_URL"],
    bearer_token=os.environ.get("AIRFLOW_API_TOKEN"),
    username=os.environ.get("AIRFLOW_API_USERNAME"),
    password=os.environ.get("AIRFLOW_API_PASSWORD"),
)
snapshot = connector.read_dag_run("orders-dag", "scheduled__2026-10-15T00:00:00+00:00")
case = snapshot.to_incident_case(
    case_id="airflow-orders-2026-10-15",
    question="Why did the orders DAG run fail?",
)
```

Configure either Bearer authentication or Basic authentication, not both. The endpoint URL is operator-controlled configuration. A production Airflow deployment should use HTTPS and a service account with read-only permissions.

### dbt artifacts

`DbtArtifactConnector` reads `manifest.json` and `run_results.json` from a completed dbt invocation. It derives model schema snapshots, model task outcomes, and dependency edges. It does not run dbt or query the warehouse.

```python
from pipeline_rca.connectors.dbt import DbtArtifactConnector

snapshot = DbtArtifactConnector("target").read()
case = snapshot.to_incident_case(
    case_id="dbt-build-2026-10-15",
    question="Which transformation model failed and what depends on it?",
)
```

The artifact folder must come from a trusted pipeline workspace. Each artifact is size-bounded, and the connector stores concise summaries and stable evidence identifiers instead of copying arbitrary raw metadata into model prompts.

### OpenLineage JSON Lines export

`OpenLineageEventFileConnector` parses a bounded JSON Lines export of OpenLineage events. It maps run lifecycle events to task status, links input and output datasets, and extracts output schema names when schema facets are present.

```python
from pipeline_rca.connectors.openlineage import OpenLineageEventFileConnector

snapshot = OpenLineageEventFileConnector("artifacts/openlineage-events.jsonl").read()
case = snapshot.to_incident_case(
    case_id="openlineage-investigation-001",
    question="What upstream datasets fed the failed job?",
)
```

The file must be exported by a trusted collector and access-controlled at the filesystem level.

## Common contracts

All adapters return `ConnectorSnapshot`, which includes:

- source identity and collection timestamp;
- normalized evidence records with stable opaque IDs;
- task observations with normalized statuses;
- lineage edges;
- schema snapshots where the source exposes schema metadata.

Call `to_incident_case(...)` to pass the observations to the existing deterministic and bounded investigation runtime. The conversion does not add benchmark truth or claim a confirmed root cause.

## Transport security and operational limits

- The HTTP transport supports GET only, applies a timeout, caps response bytes, rejects redirects, and rejects path traversal or origin changes.
- TLS is required for non-loopback HTTP destinations. Plain HTTP is permitted only on loopback for development.
- Credentials are injected by the caller and never included in exception messages or evidence summaries.
- HTTP errors expose the status code, not the upstream response body, which may contain sensitive information.
- The default HTTP response bound is 4 MB. dbt artifacts and OpenLineage event files are bounded to 20 MB by default; OpenLineage parsing is limited to 10,000 lines.
- Network and filesystem access still depend on deployment-level egress policies, service-account permissions, and file permissions. The adapters do not replace those controls.

## What remains outside this adapter layer

No cloud-warehouse SQL connector, vendor-specific data catalog, production scheduler, secret manager integration, or auto-remediation API is included. These should be separate reviewed adapters with explicit read-only credentials, allowlisted queries, pagination limits, source-specific schema tests, and integration tests against a controlled environment.
