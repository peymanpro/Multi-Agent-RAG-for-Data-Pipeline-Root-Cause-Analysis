# Schema Drift Runbook

## Symptoms

A transformation fails because a required column is missing, a downstream model stops populating a field, or a schema contract changes between a source and its consumer.

## Evidence to collect

- Compare the latest source schema with the declared consumer contract.
- Record the source dataset, schema version, observation timestamp, and required column list.
- Inspect task logs for missing-field, incompatible-type, or deserialization errors.
- Identify downstream models using the changed field through lineage metadata.

## Diagnostic procedure

1. Check whether required columns are absent from the observed schema.
2. Check for renamed fields and incompatible type changes; a renamed field may look like a missing column plus a newly introduced column.
3. Compare the last known good schema with the current schema when both snapshots are available.
4. Match the schema observation timestamp to the failed task run to avoid correlating unrelated changes.
5. Record which statements are direct observations and which remain hypotheses.

## Safe response

Do not automatically rename columns or rewrite production data. Propose a compatible mapping or producer/consumer contract change and require owner review. A missing column alone demonstrates a contract violation, not necessarily the only root cause of the incident.

## Related diagnostic codes

- `SCHEMA_REQUIRED_COLUMN_MISSING`
- `SCHEMA_DUPLICATE_COLUMN`
- `PIPELINE_TASK_FAILED`
